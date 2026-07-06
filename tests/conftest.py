"""
Shared fixtures for the test suite.

Tests run against a dedicated `docwise_test` database created (and dropped)
on the same Postgres instance as development, so pgvector behaves exactly
like production. All Gemini calls are mocked — no test touches the network.
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import psycopg2
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.models import Base, Chunk, Session
from app.main import app

TEST_DB_NAME = "docwise_test"


def _admin_conn():
    """Sync connection to the default `postgres` db to create/drop the test db."""
    url = make_url(settings.database_url)
    conn = psycopg2.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname="postgres",
    )
    conn.autocommit = True
    return conn


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Create the test database once per run, drop it at the end."""
    conn = _admin_conn()
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    conn.close()

    yield

    conn = _admin_conn()
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)")
    conn.close()


@pytest.fixture
async def engine():
    """
    Fresh engine + schema per test. NullPool avoids cross-event-loop
    connection reuse, the classic asyncpg + pytest-asyncio pitfall.
    """
    url = make_url(settings.database_url).set(database=TEST_DB_NAME)
    engine = create_async_engine(url, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db(engine):
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
async def client(engine):
    """HTTP client against the app, with get_db pointing at the test database."""
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    # The in-memory rate limiter would leak state between tests — off by
    # default; tests/test_security.py re-enables it explicitly.
    limiter.enabled = False
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    limiter.enabled = True


def fake_vector(seed: float = 0.0) -> list[float]:
    """A deterministic embedding of the configured dimensionality."""
    dims = settings.embedding_dims
    return [seed] + [0.0] * (dims - 1)


@pytest.fixture
def make_session(db):
    """Factory that inserts a Session (and optional chunks) into the test db."""

    async def _make(
        status: str = "ready",
        questions_used: int = 0,
        age_hours: float = 0,
        chunks: list[str] | None = None,
    ) -> Session:
        created = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        session = Session(
            id=uuid.uuid4(),
            filename="doc.pdf",
            status=status,
            questions_used=questions_used,
            created_at=created,
            last_active=created,
        )
        db.add(session)
        await db.flush()
        for i, content in enumerate(chunks or []):
            db.add(
                Chunk(
                    session_id=session.id,
                    content=content,
                    embedding=fake_vector(seed=float(i + 1)),
                    chunk_index=i,
                )
            )
        await db.commit()
        return session

    return _make
