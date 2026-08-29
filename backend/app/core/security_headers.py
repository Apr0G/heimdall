"""Security response headers + a request-body-size guard.

The API returns JSON only, so the CSP is maximally strict (`default-src 'none'`).
HSTS is safe to always send — browsers ignore it over plain HTTP. Uploads never
flow through the API (presigned S3 PUT), so a small body cap protects the JSON
endpoints without affecting document size — and it counts *streamed* bytes, so a
chunked-transfer request (no Content-Length) can't slip past it.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

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


class BodySizeLimitMiddleware:
    """Reject request bodies over the cap — including chunked transfers, which carry
    no Content-Length and would otherwise be buffered whole into memory when FastAPI
    parses JSON (an unauthenticated exhaustion vector via the public leads endpoint).

    Pure ASGI so it wraps `receive`: it reads the body once, aborting at the cap,
    then replays it to the app. API bodies are tiny JSON (uploads go straight to
    S3), so buffering is cheap.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        body = bytearray()
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                if len(body) > self.max_body_bytes:
                    await self._reject(send)
                    return
                more = message.get("more_body", False)
            else:  # http.disconnect (or unexpected) — stop reading, replay what we have
                more = False

        buffered = bytes(body)
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": buffered, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"detail":"Request body too large"}'})


# The interactive API docs are HTML pages that load their own scripts and
# styles, which `default-src 'none'` blanks out. main.py only serves them
# outside production, so only there is the CSP dropped for exactly these paths;
# every other header still applies, and in production they 404 with full
# headers like any other unknown path.
_DOCS_PATHS = frozenset(["/docs", "/redoc", "/openapi.json"])
_CSP = "Content-Security-Policy"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        skip_csp = settings.app_env != "production" and request.url.path in _DOCS_PATHS
        for name, value in _HEADERS.items():
            if skip_csp and name == _CSP:
                continue
            response.headers.setdefault(name, value)
        # Best-effort: don't advertise the server implementation. (uvicorn's own
        # Server header is added at the protocol layer; disable via
        # uvicorn --no-server-header in production.)
        if "server" in response.headers:
            del response.headers["server"]
        return response
