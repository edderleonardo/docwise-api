import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, documents, health, internal
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
    description="RAG chatbot — upload a PDF and ask up to 20 questions",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allows the Vercel frontend to call the backend.
# allow_origins does not expand wildcards inside a domain, so the
# Vercel subdomains need allow_origin_regex instead.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # local Next.js
    allow_origin_regex=r"https://.*\.vercel\.app",  # Vercel deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(internal.router)
