import asyncio
import uuid
from fastapi import HTTPException, UploadFile
from google.genai import errors as genai_errors
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.ingestion import chunk_and_embed
from app.db.models import Chunk, Session
from app.services.usage_service import consume_daily_quota


async def validate_upload(file: UploadFile) -> bytes:
    """
    Validate the file before processing it.
    Returns the PDF bytes if everything is fine.
    """
    # 1. Check that it is a PDF
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    max_bytes = settings.max_pdf_size_mb * 1024 * 1024

    # 2. Reject by declared size before reading the body at all
    if file.size and file.size > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_pdf_size_mb}MB",
        )

    # 3. Read and re-check the real size (the declared one can lie)
    pdf_bytes = await file.read()
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_pdf_size_mb}MB",
        )

    return pdf_bytes


async def get_active_session(session_id: uuid.UUID, db: AsyncSession) -> Session:
    """
    Look up an active session by ID.
    Raises 404 if it does not exist or has already expired.
    """
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.status != "expired")
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session


async def process_upload(
    file: UploadFile,
    db: AsyncSession,
    previous_session_id: uuid.UUID | None = None,
) -> dict:
    """
    Full upload flow:
    1. Validate the file
    2. Delete the client's previous session, if it sent one (keeps one
       active document per client without needing accounts)
    3. Create the session in the DB
    4. Generate chunks + embeddings
    5. Insert chunks into pgvector
    """
    # 1. Validate and read the PDF
    pdf_bytes = await validate_upload(file)

    # Global cost brake — every accepted upload spends daily budget
    await consume_daily_quota(db, uploads=1)

    # 2. Replace the previous document: drop its session and chunks (cascade)
    if previous_session_id:
        result = await db.execute(
            select(Session).where(Session.id == previous_session_id)
        )
        previous = result.scalar_one_or_none()
        if previous:
            await db.delete(previous)
            await db.flush()

    # 3. Create the session
    session = Session(
        id=uuid.uuid4(),
        filename=file.filename,
        status="processing",
    )
    db.add(session)
    await db.flush()  # flush to get the ID without committing yet

    # 4. Generate chunks + embeddings.
    # chunk_and_embed is synchronous (PDF parsing + blocking retries in the
    # embeddings client) — run it in a worker thread so one slow upload
    # doesn't freeze the event loop for every other request.
    try:
        chunks_data = await asyncio.to_thread(chunk_and_embed, pdf_bytes, file.filename)
    except genai_errors.APIError as e:
        if e.code == 429:
            raise HTTPException(
                status_code=429,
                detail=(
                    "The AI service is at its rate limit. "
                    "Please try again in a few minutes."
                ),
            )
        raise HTTPException(
            status_code=502,
            detail=f"The AI service failed while processing the document ({e.code}).",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 5. Insert chunks into the DB
    chunks = [
        Chunk(
            session_id=session.id,
            content=item["content"],
            embedding=item["embedding"],
            chunk_index=item["chunk_index"],
        )
        for item in chunks_data
    ]
    db.add_all(chunks)
    await db.commit()

    # 6. Update status to ready
    session.status = "ready"
    await db.commit()

    return {
        "session_id": session.id,
        "filename": session.filename,
        "status": session.status,
        "chunk_count": len(chunks),
        "message": "Document processed successfully",
    }


async def delete_session(session_id: uuid.UUID, db: AsyncSession) -> dict:
    """
    Delete the session and all its chunks (cascade).
    """
    session = await get_active_session(session_id, db)
    await db.delete(session)
    await db.commit()

    return {"message": "Session deleted successfully", "session_id": session_id}
