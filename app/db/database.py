from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,  # set True for SQL logs (dev)
    pool_size=5,  # multiple connections to the database
    max_overflow=10,  # extra connections for pike spikes in demand
    # Neon's connection pooler (PgBouncer in transaction mode) can hand each
    # query a different server connection, so asyncpg's cached prepared
    # statements break with "prepared statement does not exist" errors.
    # Disabling the cache keeps the app compatible with the pooler; direct
    # connections (local dev) just lose a micro-optimization.
    connect_args={"statement_cache_size": 0},
)

# Factory for create sessions
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # keep data after commit
)


async def get_db():
    """
    Dependency injection for FastAPI routes.
    It will create a new session for each request and close it after the request is done.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # commit changes if no exception
        except Exception:
            await session.rollback()  # rollback changes if exception
            raise
        finally:
            await session.close()  # close the session after request is done
