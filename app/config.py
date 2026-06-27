from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # AI
    gemini_api_key: str = ""

    # Internal
    internal_api_key: str = "local-dev-secret-123"

    # Session config
    session_ttl_hours: int = 24
    max_questions: int = 20
    max_pdf_size_mb: int = 10

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dims: int = 384
    top_k_results: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 50


settings = Settings()
