from datetime import date

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import DailyUsage

BUDGET_EXHAUSTED_MESSAGE = (
    "The service has reached its daily capacity. Please try again tomorrow."
)


async def consume_daily_quota(
    db: AsyncSession,
    *,
    uploads: int = 0,
    questions: int = 0,
) -> None:
    """
    Atomically increment today's global usage counters and raise 503 once the
    daily budget is exhausted. The upsert makes concurrent requests safe: the
    increment happens in the database, not in Python.

    Committed immediately so a later rollback in the same request can't undo
    the accounting.
    """
    stmt = (
        insert(DailyUsage)
        .values(day=date.today(), uploads=uploads, questions=questions)
        .on_conflict_do_update(
            index_elements=[DailyUsage.day],
            set_={
                "uploads": DailyUsage.uploads + uploads,
                "questions": DailyUsage.questions + questions,
            },
        )
        .returning(DailyUsage.uploads, DailyUsage.questions)
    )
    row = (await db.execute(stmt)).one()
    await db.commit()

    # Only enforce the budget being consumed — exhausted uploads must not
    # block chat for sessions that already exist, and vice versa.
    if uploads and row.uploads > settings.max_daily_uploads:
        raise HTTPException(status_code=503, detail=BUDGET_EXHAUSTED_MESSAGE)
    if questions and row.questions > settings.max_daily_questions:
        raise HTTPException(status_code=503, detail=BUDGET_EXHAUSTED_MESSAGE)
