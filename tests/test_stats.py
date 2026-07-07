"""Internal usage-stats endpoint: auth, history window, and persistence."""

from datetime import date, timedelta

from app.config import settings
from app.db.models import DailyUsage

AUTH = {"X-Internal-Api-Key": settings.internal_api_key}


async def seed_usage(db, *, days_ago: int, uploads: int, questions: int):
    db.add(
        DailyUsage(
            day=date.today() - timedelta(days=days_ago),
            uploads=uploads,
            questions=questions,
        )
    )
    await db.commit()


class TestAuth:
    async def test_requires_api_key(self, client):
        assert (await client.get("/internal/stats")).status_code == 401

    async def test_rejects_wrong_api_key(self, client):
        response = await client.get(
            "/internal/stats", headers={"X-Internal-Api-Key": "nope"}
        )
        assert response.status_code == 401


class TestStats:
    async def test_empty_database_returns_zeros(self, client):
        response = await client.get("/internal/stats", headers=AUTH)

        assert response.status_code == 200
        data = response.json()
        assert data["history"] == []
        assert data["totals"] == {
            "uploads": 0,
            "questions": 0,
            "days_with_activity": 0,
        }
        assert data["active_sessions"] == {"count": 0, "questions_in_progress": 0}

    async def test_history_and_totals(self, client, db):
        await seed_usage(db, days_ago=0, uploads=3, questions=12)
        await seed_usage(db, days_ago=1, uploads=1, questions=5)

        data = (await client.get("/internal/stats", headers=AUTH)).json()

        assert len(data["history"]) == 2
        # Most recent day first
        assert data["history"][0]["uploads"] == 3
        assert data["totals"] == {
            "uploads": 4,
            "questions": 17,
            "days_with_activity": 2,
        }

    async def test_days_param_limits_history_but_not_totals(self, client, db):
        await seed_usage(db, days_ago=0, uploads=2, questions=2)
        await seed_usage(db, days_ago=10, uploads=7, questions=7)

        data = (await client.get("/internal/stats?days=5", headers=AUTH)).json()

        assert len(data["history"]) == 1
        assert data["totals"]["uploads"] == 9  # totals are lifetime

    async def test_counters_survive_session_deletion(self, client, db, make_session):
        """The whole point of daily_usage: accounting outlives the sessions."""
        session = await make_session(questions_used=4)
        await seed_usage(db, days_ago=0, uploads=1, questions=4)

        before = (await client.get("/internal/stats", headers=AUTH)).json()
        assert before["active_sessions"] == {"count": 1, "questions_in_progress": 4}

        await client.delete(f"/documents/session/{session.id}")

        after = (await client.get("/internal/stats", headers=AUTH)).json()
        assert after["active_sessions"]["count"] == 0
        assert after["totals"] == {
            "uploads": 1,
            "questions": 4,
            "days_with_activity": 1,
        }

    async def test_expired_sessions_not_counted_as_active(
        self, client, make_session
    ):
        await make_session(status="expired", questions_used=9)

        data = (await client.get("/internal/stats", headers=AUTH)).json()

        assert data["active_sessions"] == {"count": 0, "questions_in_progress": 0}
