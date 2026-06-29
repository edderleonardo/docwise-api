from sentence_transformers import SentenceTransformer
from app.config import settings

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """
    Singleton pattern for the embedding model.
    It will load the model only once and reuse it for subsequent calls.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(
            settings.embedding_model,
        )
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts using the embedding model
    Converts a list of texts to vectors.
    example: ["Hello world", "How are you?"] -> [[0.1, 0.2, ...], [0.3, 0.4, ...]]

    Returns:
    A list of vectors, each vector is a list of floats to insert in pgvector column.
    """
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """
    Embed a single query using the embedding model
    Converts a single query to a vector.
    example: "Hello world" -> [0.1, 0.2, ...]
    
    Returns:
    A vector, which is a list of floats to insert in pgvector column.
    """
    model = get_model()
    embedding = model.encode(
        query,
        convert_to_numpy=True,
    )
    return embedding.tolist()
