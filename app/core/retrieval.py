import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.embeddings import embed_query
from app.db.models import Chunk


async def get_relevant_chunks(
    session_id: uuid.UUID,
    question: str,
    db: AsyncSession,
) -> list[str]:
    """
    Convert the question to vector ans search chunks more similars in pgvector
    using cosine distance.
    Operator <=> is cosine distance in pgvector. Which more near to 0 is more similar.

    Returns:
    A list of relevant chunks from the database based on the question.
    """
    # 1 Convert the question to vector
    query_embedding = await embed_query(question)
    # 2 Cosine similarity search in pgvector
    # The operator <=> is cosine distance in pgvector
    # ORDER BY distance ASC = more similar first
    result = await db.execute(
        select(Chunk.content)
        .where(Chunk.session_id == session_id)
        .order_by(Chunk.embedding.op("<=>")(query_embedding))
        .limit(settings.top_k_results)
    )

    chunks = result.scalars().all()
    return list(chunks)
