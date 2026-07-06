"""Abuse protections: rate limits, daily budget, input bounds, chunk cap."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import settings
from app.core.rate_limit import limiter

from .test_documents import PDF_FILE, mock_ingestion

REFERENCE_PDF = Path(__file__).parent.parent / "evals" / "golden" / "reference.pdf"


class TestDailyBudget:
    async def test_upload_budget_exhausted_returns_503(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(settings, "max_daily_uploads", 1)

        with mock_ingestion():
            first = await client.post("/documents/upload", files=PDF_FILE)
            second = await client.post("/documents/upload", files=PDF_FILE)

        assert first.status_code == 200
        assert second.status_code == 503
        assert "daily capacity" in second.json()["detail"]

    async def test_chat_budget_exhausted_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(settings, "max_daily_questions", 0)

        response = await client.post(
            f"/chat/{uuid.uuid4()}", json={"question": "hola?"}
        )

        assert response.status_code == 503

    async def test_upload_and_chat_budgets_are_independent(
        self, client, make_session, monkeypatch
    ):
        monkeypatch.setattr(settings, "max_daily_uploads", 0)
        session = await make_session(chunks=["content"])

        # uploads are exhausted...
        with mock_ingestion():
            upload = await client.post("/documents/upload", files=PDF_FILE)
        assert upload.status_code == 503

        # ...but chat still works (mocked LLM)
        from .test_chat import mock_llm

        p1, p2, p3 = mock_llm(tokens=["ok"])
        with p1, p2, p3:
            chat = await client.post(
                f"/chat/{session.id}", json={"question": "hola?"}
            )
        assert chat.status_code == 200


class TestRateLimit:
    async def test_upload_rate_limit_returns_429(self, client):
        limiter.enabled = True
        try:
            limit = int(settings.rate_limit_uploads.split("/")[0])
            with mock_ingestion():
                responses = [
                    await client.post("/documents/upload", files=PDF_FILE)
                    for _ in range(limit + 1)
                ]
            assert all(r.status_code == 200 for r in responses[:limit])
            assert responses[-1].status_code == 429
        finally:
            limiter.enabled = False
            limiter.reset()


class TestInputBounds:
    async def test_question_too_long_is_422(self, client, make_session):
        session = await make_session(chunks=["content"])
        response = await client.post(
            f"/chat/{session.id}", json={"question": "x" * 2001}
        )
        assert response.status_code == 422

    async def test_empty_question_is_422(self, client, make_session):
        session = await make_session(chunks=["content"])
        response = await client.post(f"/chat/{session.id}", json={"question": ""})
        assert response.status_code == 422

    async def test_oversized_declared_size_rejected_early(self, client):
        """UploadFile.size (from Content-Length of the part) is checked
        before the body is read."""
        big = b"x" * (settings.max_pdf_size_mb * 1024 * 1024 + 1)
        response = await client.post(
            "/documents/upload",
            files={"file": ("big.pdf", big, "application/pdf")},
        )
        assert response.status_code == 400


class TestChunkCap:
    def test_document_with_too_many_chunks_is_rejected(self, monkeypatch):
        """A real PDF parse (local, no network) — only embeddings are mocked."""
        from app.core.ingestion import chunk_and_embed

        monkeypatch.setattr(settings, "max_chunks_per_document", 1)
        pdf_bytes = REFERENCE_PDF.read_bytes()

        with patch("app.core.ingestion.embed_texts"):
            with pytest.raises(ValueError, match="too much text"):
                chunk_and_embed(pdf_bytes, "reference.pdf")


class TestProductionStartupCheck:
    async def test_refuses_default_internal_key_in_production(self, monkeypatch):
        from app.main import app, lifespan

        monkeypatch.setattr(settings, "environment", "production")
        with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
            async with lifespan(app):
                pass
