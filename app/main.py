import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import chat, documents, health, internal
from app.config import DEV_INTERNAL_API_KEY, settings
from app.core.rate_limit import limiter
from app.db.database import AsyncSessionLocal
from app.services.cleanup_service import cleanup_expired_sessions

# How often the background task looks for expired sessions
CLEANUP_INTERVAL_SECONDS = 3600


async def _cleanup_loop():
    """
    Deletes expired sessions on startup and then once per hour.
    Covers users who close the browser without deleting their document.
    """
    while True:
        try:
            async with AsyncSessionLocal() as db:
                deleted = await cleanup_expired_sessions(db)
                if deleted:
                    print(f"Cleanup: removed {deleted} expired session(s)")
        except Exception as e:
            # Never let a transient DB error kill the loop
            print(f"Cleanup task error: {e}")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on app startup and shutdown.
    Embeddings now come from the Gemini API, so there is no local
    model to preload — startup is instant.
    """
    # The dev fallback key is committed to a public repo — refuse to boot a
    # production deploy that forgot to set a real INTERNAL_API_KEY.
    if (
        settings.environment == "production"
        and settings.internal_api_key == DEV_INTERNAL_API_KEY
    ):
        raise RuntimeError(
            "INTERNAL_API_KEY is still the development default. "
            "Set a real secret before deploying to production."
        )

    print("Ready to serve requests.")

    cleanup_task = asyncio.create_task(_cleanup_loop())

    yield  # the app runs here

    # On shutdown — stop the background cleanup task
    print("Shutting down...")
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task


app = FastAPI(
    title="docwise API",
    description="RAG chatbot — upload a PDF and ask questions about it",
    version="0.1.0",
    lifespan=lifespan,
)

# Per-IP rate limiting (slowapi). Routes opt in with @limiter.limit(...).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allows the Vercel frontend to call the backend.
# allow_origins does not expand wildcards inside a domain, so the Vercel
# preview deployments need allow_origin_regex. Scoped to this project's
# deployments (docwise-web*) rather than every *.vercel.app site.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # local Next.js
    allow_origin_regex=r"https://docwise-web[a-z0-9-]*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(internal.router)
