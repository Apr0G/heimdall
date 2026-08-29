"""statement_timeout really cancels (LOW-17), using the exact connect_args shape
the API engine passes to asyncpg — and SET LOCAL lifts it inside a transaction,
which is what alembic/env.py relies on so an index build is never capped.

A fresh engine with a 500 ms cap keeps the suite fast; no schema is touched.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import session as app_session

pytestmark = pytest.mark.asyncio


def _capped_engine(url: str):
    args = {
        **app_session.connect_args,
        "ssl": False,  # throwaway local Postgres, no certificate
        "server_settings": {
            **app_session.connect_args["server_settings"],
            "statement_timeout": "500",
        },
    }
    return create_async_engine(url, connect_args=args)


async def test_statement_past_the_cap_is_cancelled(migrated):
    engine = _capped_engine(migrated)
    try:
        async with engine.connect() as conn:
            with pytest.raises(DBAPIError) as exc:
                await conn.execute(text("SELECT pg_sleep(2)"))
            assert "statement timeout" in str(exc.value).lower()
    finally:
        await engine.dispose()


async def test_set_local_lifts_the_cap_for_the_transaction(migrated):
    engine = _capped_engine(migrated)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET LOCAL statement_timeout = 0"))
            await conn.execute(text("SELECT pg_sleep(0.8)"))  # past the cap, allowed
        # Next transaction on the pool: the startup setting is back.
        async with engine.connect() as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(text("SELECT pg_sleep(0.8)"))
    finally:
        await engine.dispose()
