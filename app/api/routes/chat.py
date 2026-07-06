import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.services.chat_service import generate_chat_response
from app.services.usage_service import consume_daily_quota

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    # Bounded so nobody streams megabytes into the expansion/embedding calls
    question: str = Field(min_length=1, max_length=2000)


@router.post("/{session_id}")
@limiter.limit(settings.rate_limit_chat)
async def chat(
    request: Request,
    session_id: uuid.UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Streams the RAG response as Server-Sent Events.
    Each token arrives as a separate SSE event.
    """
    # Global cost brake — checked before the stream starts so the client
    # gets a clean 503 instead of an in-band error.
    await consume_daily_quota(db, questions=1)

    async def event_stream():
        try:
            async for token in generate_chat_response(session_id, body.question, db):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        except genai_errors.APIError as e:
            if e.code == 429:
                yield (
                    "data: [ERROR] The AI service is at its rate limit. "
                    "Please wait a minute and try again.\n\n"
                )
            else:
                yield (
                    f"data: [ERROR] The AI service failed ({e.code}). "
                    "Please try again.\n\n"
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )
