"""Expired-session cleanup: the service, the cascade, and the internal endpoint."""

from sqlalchemy import func, select

from app.config import settings
from app.db.models import Chunk, Session
from app.services.cleanup_service import cleanup_expired_sessions


class TestCleanupService:
    async def test_deletes_only_expired_sessions(self, db, make_session):
        expired = await make_session(age_hours=settings.session_ttl_hours + 1)
        fresh = await make_session(age_hours=1)

        deleted = await cleanup_expired_sessions(db)

        assert deleted == 1
        assert (await db.get(Session, expired.id)) is None
        assert (await db.get(Session, fresh.id)) is not None

    async def test_cascade_removes_chunks(self, db, make_session):
        expired = await make_session(
            age_hours=settings.session_ttl_hours + 1, chunks=["a", "b"]
        )

        await cleanup_expired_sessions(db)

        remaining = (
            await db.execute(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.session_id == expired.id)
            )
        ).scalar()
        assert remaining == 0

    async def test_nothing_to_delete_returns_zero(self, db, make_session):
        await make_session(age_hours=1)
        assert await cleanup_expired_sessions(db) == 0


class TestInternalEndpoint:
    async def test_requires_api_key(self, client):
        response = await client.post("/internal/cleanup")
        assert response.status_code == 401

    async def test_rejects_wrong_api_key(self, client):
        response = await client.post(
            "/internal/cleanup", headers={"X-Internal-Api-Key": "nope"}
        )
        assert response.status_code == 401

    async def test_runs_cleanup_with_valid_key(self, client, make_session):
        await make_session(age_hours=settings.session_ttl_hours + 1)

        response = await client.post(
            "/internal/cleanup",
            headers={"X-Internal-Api-Key": settings.internal_api_key},
        )

        assert response.status_code == 200
        assert response.json() == {"sessions_deleted": 1}
