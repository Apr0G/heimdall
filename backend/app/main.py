import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.admin_users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.leads import router as leads_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.core.security_headers import BodySizeLimitMiddleware, SecurityHeadersMiddleware

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

# Fail the SERVING API loudly if production has no Redis (the in-memory
# rate-limit fallback silently defeats the AI spend cap + login throttle). Lives
# here, not in Settings, so one-off admin tasks (alembic migrate, export,
# dispose, provision) — which run APP_ENV=production without Redis — still boot.
settings.require_redis_in_production()

# Swagger UI, ReDoc, and the OpenAPI schema expose the full API surface (every
# route, param, and shape) — useful in dev, but free reconnaissance for an
# attacker in prod. Serve them only outside production; in prod all three 404.
_docs_enabled = settings.app_env != "production"
app = FastAPI(
    title="Heimdall API",
    version="0.1.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Rate limiting (default limits applied to every route; stricter per-route limits
# are declared on the auth + AI endpoints). 429 responses carry Retry-After.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Streamed-body-size guard (counts chunked bodies too, so a public endpoint
# can't be memory-exhausted), wrapped by the security-headers middleware.
# add_middleware PREPENDS, so the later call is the outer layer — headers must
# be added after the body guard or its 413s ship without them.
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Exact frontend origin only; explicit methods/headers (no wildcards). Presigned
# S3 uploads go browser->S3 directly. Every method a router registers must be
# listed here or the browser's preflight fails — test_cors_methods pins that.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Never leak internals to clients — full detail to logs, generic body out."""
    logger.exception(
        "unhandled error", extra={"context": {"path": request.url.path, "method": request.method}}
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health_router)
app.include_router(admin_router)
app.include_router(admin_users_router)
app.include_router(auth_router)
app.include_router(cases_router)
app.include_router(documents_router)
app.include_router(leads_router)
