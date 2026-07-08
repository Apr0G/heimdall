import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# RDS enforces TLS (rds.force_ssl). For dev we require TLS but skip certificate
# verification; Part 12 hardening should pin the RDS CA bundle instead of
# disabling verification.
_ssl_context = ssl.create_default_context()
_ssl_context.check_hostname = False
_ssl_context.verify_mode = ssl.CERT_NONE

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,  # drop dead connections instead of erroring a request
    pool_size=10,
    max_overflow=10,  # up to 20 connections per task; RDS t4g.micro allows ~112
    pool_timeout=30,
    pool_recycle=1800,  # recycle every 30 min to avoid stale server-side closes
    connect_args={"ssl": _ssl_context},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session per request."""
    async with AsyncSessionLocal() as session:
        yield session
