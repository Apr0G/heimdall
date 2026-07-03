"""Rate limiting (SlowAPI).

Keying: authenticated requests key on the Cognito ``sub`` (read from the bearer
token WITHOUT cryptographic verification — forging it only shares your own
bucket), everything else keys on client IP. Storage is Redis when ``REDIS_URL``
is set (survives multiple containers) and in-memory otherwise (dev/test).

Fail-open: ``swallow_errors`` means a storage outage lets requests through rather
than taking the API down — availability of PHI care over strict throttling.
"""

from jose import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings


def rate_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            sub = jwt.get_unverified_claims(auth.split(" ", 1)[1]).get("sub")
            if sub:
                # False positive: an internal rate-limit key, never rendered as
                # HTTP output; `sub` is a JWT-claim UUID. Suppress the Flask rule.
                return f"user:{sub}"  # nosemgrep
        except Exception:
            # Malformed token — fall through to IP keying.
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=rate_key,
    default_limits=[settings.rate_limit_general],
    storage_uri=settings.redis_url or "memory://",
    strategy="moving-window",
    headers_enabled=True,  # emit X-RateLimit-* and Retry-After
    swallow_errors=True,  # fail-open on storage errors
)
