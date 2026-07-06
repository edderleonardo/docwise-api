"""Chat service: session validation, quota, retrieval scoping, and streaming."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.models import Session
from app.services.chat_service import generate_chat_response, validate_chat_request

from .conftest import fake_vector


def mock_llm(tokens: list[str]):
    """Patch the two Gemini touchpoints of the chat pipeline."""

    async def fake_stream(question, chunks):
        for token in tokens:
            yield token

    return (
        patch(
            "app.services.chat_service.expand_query",
            new=AsyncMock(side_effect=lambda q: q),
        ),
        patch("app.services.chat_service.stream_response", new=fake_stream),
        patch(
            "app.core.retrieval.embed_query",
            new=AsyncMock(return_value=fake_vector(1.0)),
        ),
    )


class TestValidateChatRequest:
    async def test_unknown_session_raises(self, db):
        with pytest.raises(ValueError, match="not found"):
            await validate_chat_request(uuid.uuid4(), db)

    async def test_processing_session_raises(self, db, make_session):
        session = await make_session(status="processing")
        with pytest.raises(ValueError, match="not found|not ready"):
            await validate_chat_request(session.id, db)

    async def test_quota_reached_raises(self, db, make_session):
        session = await make_session(questions_used=settings.max_questions)
        with pytest.raises(ValueError, match="limit"):
            await validate_chat_request(session.id, db)

    async def test_ready_session_passes(self, db, make_session):
        session = await make_session(questions_used=settings.max_questions - 1)
        result = await validate_chat_request(session.id, db)
        assert result.id == session.id


class TestGenerateChatResponse:
    async def test_streams_tokens_and_increments_quota(self, db, make_session):
        session = await make_session(chunks=["relevant content"])
        p1, p2, p3 = mock_llm(tokens=["Hello", " world"])

        with p1, p2, p3:
            tokens = [
                t
                async for t in generate_chat_response(session.id, "question?", db)
            ]

        assert tokens == ["Hello", " world"]

        refreshed = (
            await db.execute(select(Session).where(Session.id == session.id))
        ).scalar_one()
        assert refreshed.questions_used == 1

    async def test_retrieval_is_scoped_to_the_session(self, db, make_session):
        """Chunks from another session must never leak into the answer."""
        mine = await make_session(chunks=["my document"])
        await make_session(chunks=["someone else's document"])

        captured: dict = {}

        async def fake_stream(question, chunks):
            captured["chunks"] = chunks
            yield "ok"

        p1, _, p3 = mock_llm(tokens=[])
        with p1, patch(
            "app.services.chat_service.stream_response", new=fake_stream
        ), p3:
            async for _ in generate_chat_response(mine.id, "question?", db):
                pass

        assert captured["chunks"] == ["my document"]

    async def test_session_without_chunks_raises(self, db, make_session):
        session = await make_session(chunks=[])
        p1, p2, p3 = mock_llm(tokens=[])

        with p1, p2, p3:
            with pytest.raises(ValueError, match="No content"):
                async for _ in generate_chat_response(session.id, "question?", db):
                    pass


class TestChatEndpoint:
    async def test_streams_sse_and_finishes_with_done(self, client, make_session):
        session = await make_session(chunks=["content"])
        p1, p2, p3 = mock_llm(tokens=["Hi"])

        with p1, p2, p3:
            response = await client.post(
                f"/chat/{session.id}", json={"question": "hola?"}
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "data: Hi\n\n" in response.text
        assert response.text.endswith("data: [DONE]\n\n")

    async def test_unknown_session_streams_error_event(self, client):
        p1, p2, p3 = mock_llm(tokens=[])
        with p1, p2, p3:
            response = await client.post(
                f"/chat/{uuid.uuid4()}", json={"question": "hola?"}
            )

        assert response.status_code == 200  # SSE: errors travel in-band
        assert "[ERROR]" in response.text
