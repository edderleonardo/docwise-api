from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import documents, health
from app.core.embeddings import get_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on app startup and shutdown.
    We load the model here so that the cold start
    does not affect the user's first request.
    """
    # On startup — load the model into memory
    print("Loading embedding model...")
    get_model()
    print("Model loaded. Ready to serve requests.")

    yield  # the app runs here

    # On shutdown — cleanup if needed
    print("Shutting down...")


app = FastAPI(
    title="docwise API",
    description="RAG chatbot — upload a PDF and ask up to 20 questions",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allows the Vercel frontend to call the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # local Next.js
        "https://*.vercel.app",  # Vercel deployment
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(documents.router)
