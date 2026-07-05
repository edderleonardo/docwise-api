import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.llm import expand_query, stream_response
from app.core.retrieval import get_relevant_chunks
from app.db.models import Session


async def validate_chat_request(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> Session:
    """
    Checks the session exists, is ready, and hasn't hit the question limit.
    """
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.status == "ready",
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise ValueError("Session not found or document not ready")

    if session.questions_used >= session.max_questions:
        raise ValueError(
            f"Question limit reached ({session.max_questions} questions max)"
        )

    return session


async def increment_question_count(
    session: Session,
    db: AsyncSession,
) -> None:
    """
    Updates the question counter and last_active timestamp.
    """
    session.questions_used += 1
    session.last_active = datetime.now(timezone.utc)
    await db.commit()


async def generate_chat_response(
    session_id: uuid.UUID,
    question: str,
    db: AsyncSession,
):
    """
    Full RAG pipeline:
    1. Validate the session and quota
    2. Retrieve relevant chunks
    3. Stream the LLM response
    4. Update the question counter
    """
    session = await validate_chat_request(session_id, db)

    # Rewrite the question so vector search matches the document's vocabulary;
    # the LLM still receives the user's original question.
    search_query = await expand_query(question)
    chunks = await get_relevant_chunks(session_id, search_query, db)

    if not chunks:
        raise ValueError("No content available for this document")

    async for token in stream_response(question, chunks):
        yield token

    await increment_question_count(session, db)
