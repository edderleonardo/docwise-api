from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Session


async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """
    Deletes sessions inactive for longer than the configured TTL.
    Chunks are removed automatically via cascade delete.
    Returns the number of sessions deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.session_ttl_hours)

    result = await db.execute(select(Session).where(Session.last_active < cutoff))
    expired_sessions = result.scalars().all()

    if not expired_sessions:
        return 0

    await db.execute(delete(Session).where(Session.last_active < cutoff))
    await db.commit()

    return len(expired_sessions)
