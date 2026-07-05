from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify that the API is running.
    Returns a simple JSON response indicating the service status.
    """
    return {"status": "ok"}


@router.get("/config", tags=["Health"])
async def public_config():
    """
    Public limits the frontend needs to render accurate copy and
    validate uploads. Single source of truth: the backend settings.
    """
    return {
        "max_questions": settings.max_questions,
        "max_pdf_size_mb": settings.max_pdf_size_mb,
        "session_ttl_hours": settings.session_ttl_hours,
    }
