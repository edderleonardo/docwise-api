"""Upload, status, and delete endpoints — chunk_and_embed is always mocked."""

import uuid
from unittest.mock import patch

from sqlalchemy import func, select

from app.db.models import Chunk, Session

from .conftest import fake_vector

FAKE_CHUNKS = [
    {"content": "first chunk", "embedding": fake_vector(1.0), "chunk_index": 0},
    {"content": "second chunk", "embedding": fake_vector(2.0), "chunk_index": 1},
]

PDF_FILE = {"file": ("doc.pdf", b"%PDF-fake", "application/pdf")}


def mock_ingestion():
    return patch(
        "app.services.document_service.chunk_and_embed", return_value=FAKE_CHUNKS
    )


async def count_chunks(db, session_id) -> int:
    result = await db.execute(
        select(func.count()).select_from(Chunk).where(Chunk.session_id == session_id)
    )
    return result.scalar()


async def get_session(db, session_id) -> Session | None:
    """Query by id with a real SELECT — db.get() would return the object
    cached in the identity map even after another session deleted the row."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


class TestUpload:
    async def test_rejects_non_pdf(self, client):
        response = await client.post(
            "/documents/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400
        assert "Only PDF" in response.json()["detail"]

    async def test_rejects_oversized_pdf(self, client):
        from app.config import settings

        big = b"x" * (settings.max_pdf_size_mb * 1024 * 1024 + 1)
        response = await client.post(
            "/documents/upload",
            files={"file": ("big.pdf", big, "application/pdf")},
        )
        assert response.status_code == 400
        assert "too large" in response.json()["detail"].lower()

    async def test_upload_creates_ready_session_with_chunks(self, client, db):
        with mock_ingestion():
            response = await client.post("/documents/upload", files=PDF_FILE)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["chunk_count"] == len(FAKE_CHUNKS)

        session_id = uuid.UUID(body["session_id"])
        assert await count_chunks(db, session_id) == len(FAKE_CHUNKS)

    async def test_upload_replaces_previous_session(self, client, db, make_session):
        previous = await make_session(chunks=["old chunk"])

        with mock_ingestion():
            response = await client.post(
                "/documents/upload",
                files=PDF_FILE,
                data={"previous_session_id": str(previous.id)},
            )

        assert response.status_code == 200
        # previous session and its chunks are gone
        assert (await get_session(db, previous.id)) is None
        assert await count_chunks(db, previous.id) == 0

    async def test_upload_ignores_unknown_previous_session(self, client):
        with mock_ingestion():
            response = await client.post(
                "/documents/upload",
                files=PDF_FILE,
                data={"previous_session_id": str(uuid.uuid4())},
            )
        assert response.status_code == 200


class TestStatus:
    async def test_returns_session_info(self, client, make_session):
        session = await make_session(questions_used=3)

        response = await client.get(f"/documents/status/{session.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == str(session.id)
        assert body["questions_used"] == 3
        assert body["max_questions"] == session.max_questions

    async def test_unknown_session_is_404(self, client):
        response = await client.get(f"/documents/status/{uuid.uuid4()}")
        assert response.status_code == 404


class TestDelete:
    async def test_delete_cascades_to_chunks(self, client, db, make_session):
        session = await make_session(chunks=["a", "b", "c"])

        response = await client.delete(f"/documents/session/{session.id}")

        assert response.status_code == 200
        assert (await get_session(db, session.id)) is None
        assert await count_chunks(db, session.id) == 0

    async def test_delete_unknown_session_is_404(self, client):
        response = await client.delete(f"/documents/session/{uuid.uuid4()}")
        assert response.status_code == 404
