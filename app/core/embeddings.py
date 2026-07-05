import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import settings

# Same client/key as the chat LLM
client = genai.Client(api_key=settings.gemini_api_key)

# Max texts per embed_content call (API limit)
BATCH_SIZE = 100

# Bursty batches trip the free tier's per-minute limit — wait and retry
RETRY_DELAY_SECONDS = 30
MAX_RETRIES = 2


def _embed_batch(batch: list[str]) -> list[list[float]]:
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = client.models.embed_content(
                model=settings.embedding_model,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=settings.embedding_dims,
                ),
            )
            return [e.values for e in result.embeddings]
        except genai_errors.APIError as e:
            if e.code == 429 and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            raise
    return []  # unreachable


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed document chunks via the Gemini embeddings API.
    Batched to respect the per-request limit; task_type RETRIEVAL_DOCUMENT
    optimizes the vectors for being searched against.

    Returns a list of vectors ready for the pgvector column.
    """
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        embeddings.extend(_embed_batch(texts[i : i + BATCH_SIZE]))
    return embeddings


async def embed_query(query: str) -> list[float]:
    """
    Embed a search query (async so it doesn't block the event loop).
    task_type RETRIEVAL_QUERY pairs with RETRIEVAL_DOCUMENT above.
    """
    result = await client.aio.models.embed_content(
        model=settings.embedding_model,
        contents=query,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=settings.embedding_dims,
        ),
    )
    return result.embeddings[0].values
