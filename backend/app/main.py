import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.leads import router as leads_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.core.security_headers import SecurityHeadersMiddleware

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Heimdall API", version="0.1.0")

# Rate limiting (default limits applied to every route; stricter per-route limits
# are declared on the auth + AI endpoints). 429 responses carry Retry-After.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security response headers + body-size guard (outermost so it wraps everything).
app.add_middleware(SecurityHeadersMiddleware)

# Exact frontend origin only; explicit methods/headers (no wildcards). Presigned
# S3 uploads go browser->S3 directly, so the API only needs GET/POST/OPTIONS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
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
app.include_router(auth_router)
app.include_router(cases_router)
app.include_router(documents_router)
app.include_router(leads_router)
