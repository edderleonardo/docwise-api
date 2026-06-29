import uuid

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

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
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF and generate embeddings.
    Only 1 active document is allowed per session.
    """
    result = await process_upload(file, db)
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
