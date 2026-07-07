import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.schemas.internal import CleanupResponse, StatsResponse
from app.services.cleanup_service import cleanup_expired_sessions
from app.services.usage_service import get_usage_stats

router = APIRouter(prefix="/internal", tags=["internal"])

api_key_header = APIKeyHeader(name="X-Internal-Api-Key", auto_error=False)


def verify_internal_key(api_key: str = Security(api_key_header)) -> None:
    """
    Guard for internal endpoints.
    Compares the X-Internal-Api-Key header against the configured secret.
    """
    if not api_key or not secrets.compare_digest(
        api_key, settings.internal_api_key
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.post(
    "/cleanup",
    response_model=CleanupResponse,
    dependencies=[Depends(verify_internal_key)],
)
async def cleanup_sessions(db: AsyncSession = Depends(get_db)):
    """
    Delete sessions older than the configured TTL.
    Their chunks (and embeddings) are removed via cascade.
    Meant to be called by a cron job, not by end users.
    """
    deleted = await cleanup_expired_sessions(db)
    return {"sessions_deleted": deleted}


@router.get(
    "/stats",
    response_model=StatsResponse,
    dependencies=[Depends(verify_internal_key)],
)
async def usage_stats(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Usage statistics: per-day history and lifetime totals (from daily_usage,
    which survives session cleanup) plus a snapshot of active sessions.
    """
    return await get_usage_stats(db, days=days)
