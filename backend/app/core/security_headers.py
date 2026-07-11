"""Security response headers + a coarse request-body-size guard.

The API returns JSON only, so the CSP is maximally strict (`default-src 'none'`).
HSTS is safe to always send — browsers ignore it over plain HTTP. Uploads never
flow through the API (presigned S3 PUT), so a small body cap protects the JSON
endpoints without affecting document size.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

# JSON payloads are tiny; document bytes go straight to S3, not through here.
DEFAULT_MAX_BODY_BYTES = 1_000_000  # 1 MB

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    # API responses (incl. the letter PDF) carry PHI — keep them out of browser
    # disk caches on shared machines (§164.312 minimum-necessary / transmission).
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > self.max_body_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})

        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        # Best-effort: don't advertise the server implementation. (uvicorn's own
        # Server header is added at the protocol layer; disable via
        # uvicorn --no-server-header in production.)
        if "server" in response.headers:
            del response.headers["server"]
        return response
