from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# Development-only fallback. The app refuses to start in production with this
# value — see the lifespan check in app/main.py.
DEV_INTERNAL_API_KEY = "local-dev-secret-123"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # "development" | "production" — production enforces stricter startup checks
    environment: str = "development"

    # Database
    database_url: str

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """
        Accept the connection string exactly as providers hand it out.
        Neon/Heroku-style URLs say `postgresql://` and append
        `?sslmode=require&channel_binding=require` — asyncpg needs the
        `postgresql+asyncpg://` driver and rejects those query params
        (it negotiates SSL on its own), so normalize instead of crashing
        on the first query.
        """
        url = make_url(v.strip())
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+asyncpg")
        query = {
            k: val
            for k, val in url.query.items()
            if k not in ("sslmode", "channel_binding")
        }
        return url.set(query=query).render_as_string(hide_password=False)

    # AI
    gemini_api_key: str = ""

    # Internal
    internal_api_key: str = DEV_INTERNAL_API_KEY

    # Abuse protection — per-IP rate limits (slowapi syntax)
    rate_limit_uploads: str = "10/hour"
    rate_limit_chat: str = "30/minute"

    # Abuse protection — global daily budget (cost brake for the whole service,
    # not per user; the API returns 503 once exhausted). Sized for a portfolio
    # demo: caps the worst-case Gemini bill at roughly $3/day under attack.
    max_daily_uploads: int = 50
    max_daily_questions: int = 500

    # A 10MB PDF can decompress to far more text than it weighs — cap the
    # number of chunks a single document may produce
    max_chunks_per_document: int = 500

    # Session config
    session_ttl_hours: int = 24
    max_questions: int = 20
    max_pdf_size_mb: int = 10

    # Embeddings — Gemini API (multilingual, same key as chat)
    embedding_model: str = "gemini-embedding-001"
    embedding_dims: int = 768
    gemini_model: str = "gemini-3.5-flash"
    top_k_results: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 50


settings = Settings()
