import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
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

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )
