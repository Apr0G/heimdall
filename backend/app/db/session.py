import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# DB TLS. When DB_SSL_CA_BUNDLE points at the RDS CA bundle (shipped at
# /app/rds-ca.pem), verify the server cert AND hostname (verify-full). Otherwise
# require TLS but skip verification — RDS is private + force_ssl, so traffic is
# still encrypted; this is the safe default until a deploy is verified with the CA
# (the /healthz probe does not touch the DB, so a bad cert config fails silently).
if settings.db_ssl_ca_bundle:
    _ssl_context = ssl.create_default_context(cafile=settings.db_ssl_ca_bundle)
    # check_hostname=True and verify_mode=CERT_REQUIRED are the defaults here.
else:
    _ssl_context = ssl.create_default_context()
    _ssl_context.check_hostname = False
    _ssl_context.verify_mode = ssl.CERT_NONE

# Fall back to a non-connecting placeholder when DATABASE_URL is unset, so the
# module imports (and /healthz + the test suite run) without a database — the
# engine only connects on first real use. Real deployments always set the URL.
_database_url = settings.database_url or "postgresql+asyncpg://placeholder/placeholder"

# Applied by the server on every pooled connection (asyncpg passes them as
# startup parameters; values must be strings, bare integers read as ms). Without
# a cap, one statement stuck behind an external lock holder pins its connection
# for good, and the pool (10 + 10 overflow) drains behind it. Migrations reset
# both inside their transaction (alembic/env.py); the one-off scripts open their
# own engines and never see these.
connect_args = {
    "ssl": _ssl_context,
    "server_settings": {
        "statement_timeout": str(settings.db_statement_timeout_ms),
        "lock_timeout": str(settings.db_lock_timeout_ms),
    },
}

engine = create_async_engine(
    _database_url,
    echo=False,
    # PHI CONTROL (hard rule 2), not a tuning knob. SQLAlchemy's StatementError
    # appends "[SQL: ...] [parameters: {...}]" to its str() by default, so any
    # failing INSERT/UPDATE renders its bound values — claim numbers, payer names,
    # patient initials, extracted clinical JSON — into the traceback. Both the
    # pipeline's logger.exception and main.py's global handler write that traceback
    # to CloudWatch, and core/logging._redact only masks SSN shapes and long digit
    # runs, so none of that would be caught. This suppresses the parameter echo at
    # the source, independently of whichever schema bound happens to be violated.
    hide_parameters=True,
    pool_pre_ping=True,  # drop dead connections instead of erroring a request
    pool_size=10,
    max_overflow=10,  # up to 20 connections per task; RDS t4g.micro allows ~112
    pool_timeout=30,
    pool_recycle=1800,  # recycle every 30 min to avoid stale server-side closes
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session per request."""
    async with AsyncSessionLocal() as session:
        yield session
