from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import DailyUsage, Session

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


async def get_usage_stats(db: AsyncSession, *, days: int = 30) -> dict:
    """
    Usage statistics for the internal stats endpoint.

    History and totals come from daily_usage, which survives session cleanup —
    counters are added the moment a request is accepted, so deleting a session
    later never loses accounting. Only the active-sessions block is a snapshot
    of right now.
    """
    since = date.today() - timedelta(days=days - 1)
    history = (
        (
            await db.execute(
                select(DailyUsage)
                .where(DailyUsage.day >= since)
                .order_by(DailyUsage.day.desc())
            )
        )
        .scalars()
        .all()
    )

    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(DailyUsage.uploads), 0),
                func.coalesce(func.sum(DailyUsage.questions), 0),
                func.count(),
            )
        )
    ).one()

    active = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Session.questions_used), 0),
            ).where(Session.status != "expired")
        )
    ).one()

    return {
        "history": [
            {"day": row.day, "uploads": row.uploads, "questions": row.questions}
            for row in history
        ],
        "totals": {
            "uploads": totals[0],
            "questions": totals[1],
            "days_with_activity": totals[2],
        },
        "active_sessions": {
            "count": active[0],
            "questions_in_progress": active[1],
        },
    }
