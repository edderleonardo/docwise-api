import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic trackea estos modelos para autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera SQL puro sin conectarse a la DB."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Se conecta a la DB y aplica los cambios."""
    connectable = create_async_engine(settings.database_url)

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda conn: context.configure(
                connection=conn,
                target_metadata=target_metadata,
            )
        )
        async with connection.begin():
            await connection.run_sync(lambda conn: context.run_migrations())

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
