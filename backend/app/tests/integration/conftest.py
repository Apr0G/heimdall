"""Fixtures for tests that need a real PostgreSQL.

Skipped entirely unless TEST_DATABASE_URL is set, so `pytest` on a laptop with no
database behaves exactly as before. CI sets it against a service container.

The schema is built with `alembic upgrade head`, never `Base.metadata.create_all`:
the `set_updated_at` trigger and the Postgres enums live in the migrations, and
stall detection depends on that trigger. create_all would produce a schema these
tests pass against while testing nothing.

Connections here disable TLS. The app engine mandates it (RDS is force_ssl), but
a throwaway local/CI Postgres has no certificate; migrations run through alembic's
injected-connection hook so production's TLS setup is not touched.
"""

import asyncio
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[3]
_NO_TLS = {"ssl": False}


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set — integration tests need a real Postgres")
    return url


@pytest.fixture(scope="session", autouse=True)
def migrated(db_url: str) -> str:
    """Build the schema once per session, the same way production builds it."""

    # Migration 0007 creates the limited `heimdall_app` role and refuses to run
    # without a password for it. Synthetic and test-only — this database is
    # thrown away, and no real credential ever belongs in the suite. Alphanumeric
    # because the migration rejects anything else rather than escape it into DDL.
    os.environ.setdefault("APP_DB_PASSWORD", "testonlynotarealsecret")

    def _upgrade(sync_connection) -> None:
        cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        cfg.attributes["connection"] = sync_connection
        command.upgrade(cfg, "head")

    async def _run() -> None:
        engine = create_async_engine(db_url, connect_args=_NO_TLS)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(_upgrade)
        finally:
            await engine.dispose()

    asyncio.run(_run())
    return db_url


@pytest_asyncio.fixture
async def engine(migrated: str):
    eng = create_async_engine(migrated, connect_args=_NO_TLS)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessions(engine):
    """Session factory. Each call opens its own connection, which is what makes
    the concurrency tests real — two sessions contend for an actual row lock."""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def tenant(sessions):
    """A practice + user to own the test cases. Unique per test, so tests do not
    interfere and nothing needs truncating between them."""
    from app.models import Practice, User

    async with sessions() as s:
        practice = Practice(name="Test Practice")
        s.add(practice)
        await s.flush()
        user = User(
            practice_id=practice.id,
            cognito_sub=f"sub-{uuid.uuid4()}",
            email=f"{uuid.uuid4()}@heimdall.test",
            role="doctor",
        )
        s.add(user)
        await s.commit()
        return user
