import asyncio
from logging.config import fileConfig

from sqlalchemy import text
from sqlalchemy.engine import Connection

import app.models  # noqa: F401  -- imported for the side effect of populating Base.metadata
from alembic import context
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
        # The app engine caps every connection with statement_timeout /
        # lock_timeout (db/session.py) — right for request traffic, wrong for an
        # index build or a table rewrite on a large table. SET LOCAL lifts both
        # for exactly this transaction. It must run INSIDE begin_transaction():
        # a statement before context.configure() would autobegin a transaction
        # alembic then treats as external and never commits.
        connection.execute(text("SET LOCAL statement_timeout = 0"))
        connection.execute(text("SET LOCAL lock_timeout = 0"))
        context.run_migrations()


async def run_async_migrations() -> None:
    # Reuse the app's async engine (configured with the RDS SSL context).
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    # Offline (`--sql`) compiles with literal_binds, which would inline the
    # heimdall_app password 0007 binds as a parameter. Refuse rather than emit
    # a credential into a script or CI log; review migrations online.
    raise SystemExit(
        "Offline (--sql) migrations are disabled: 0007 binds the app DB password and "
        "literal_binds would print it. Run `alembic upgrade head` online instead."
    )


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
