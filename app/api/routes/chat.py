import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from google.genai import errors as genai_errors
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.chat_service import generate_chat_response

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


@router.post("/{session_id}")
async def chat(
    session_id: uuid.UUID,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Streams the RAG response as Server-Sent Events.
    Each token arrives as a separate SSE event.
    """

    async def event_stream():
        try:
            async for token in generate_chat_response(session_id, request.question, db):
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
