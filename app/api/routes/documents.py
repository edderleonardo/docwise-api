import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.models import Session
from app.schemas.document import DeleteResponse, StatusResponse, UploadResponse
from app.services.document_service import (
    delete_session,
    get_active_session,
    process_upload,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
@limiter.limit(settings.rate_limit_uploads)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    previous_session_id: uuid.UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF and generate embeddings.
    Send previous_session_id when replacing a document so the old
    session (and its chunks) is deleted instead of lingering until the TTL.
    """
    result = await process_upload(file, db, previous_session_id)
    return result


@router.get("/status/{session_id}", response_model=StatusResponse)
async def get_status(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Return the current status of a session.
    """
    session = await get_active_session(session_id, db)
    return session


@router.delete("/session/{session_id}", response_model=DeleteResponse)
async def delete_document(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete the session and all its chunks.
    Use when the user wants to switch documents.
    """
    result = await delete_session(session_id, db)
    return result
