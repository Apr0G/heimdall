import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection

import app.models  # noqa: F401  -- imported for the side effect of populating Base.metadata
from alembic import context
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # This schema leans heavily on server defaults (now(), 'draft',
        # '{}'::text[], uuid_generate_v4()). Without this, autogenerate silently
        # misses default drift, so a model whose default no longer matches the
        # column produces an empty migration and a wrong value at runtime.
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Reuse the app's async engine (configured with the RDS SSL context).
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests inject an already-open connection (a throwaway local Postgres that
    # speaks no TLS) via config.attributes. Production and the CLI never set it
    # and fall through to the app engine above, TLS context and all.
    injected = config.attributes.get("connection")
    if injected is not None:
        do_run_migrations(injected)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
