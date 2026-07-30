"""Rate limiting (SlowAPI).

Keying: authenticated requests key on the Cognito ``sub`` (read from the session
token WITHOUT cryptographic verification — forging it only shares your own
bucket), everything else keys on client IP. Storage is Redis when ``REDIS_URL``
is set (survives multiple containers) and in-memory otherwise (dev/test).

The token is read from the ``hd_session`` cookie FIRST and the ``Authorization``
header second — the same precedence ``core/auth.py:get_current_user`` uses. This
ordering matters: Heimdall authenticates browsers by cookie and nothing in the
frontend ever sets an Authorization header, so a header-only lookup silently
degraded every authenticated limit to a per-IP bucket. That broke the AI spend cap
in one direction (any IP rotation mints a fresh 50/day allowance) and availability
in the other (a whole practice behind one office NAT shares one bucket and 429s on
ordinary PHI reads).

Fail-open: ``swallow_errors`` means a storage outage lets requests through rather
than taking the API down — availability of PHI care over strict throttling.
"""

from jose import jwt
from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from starlette.requests import Request

from app.core.auth import AUTH_COOKIE
from app.core.config import settings
from app.core.net import client_ip


def ip_key(request: Request) -> str:
    """IP-only key for PUBLIC endpoints (login, leads). Never trusts a bearer token:
    an unauthenticated caller can forge a JWT `sub` to mint a fresh bucket per
    request and bypass the limit entirely. The real client IP comes from
    X-Forwarded-For behind the ALB (not the ALB's own IP)."""
    return f"ip:{client_ip(request) or 'unknown'}"


def _session_token(request: Request) -> str | None:
    """The caller's session token, cookie first then bearer header — the SAME
    precedence as core/auth.py:get_current_user. If these two ever disagree about
    where the token lives, the limiter silently stops limiting per user."""
    cookie = request.cookies.get(AUTH_COOKIE)
    if cookie:
        return cookie
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return None


def rate_key(request: Request) -> str:
    """Key for AUTHENTICATED routes: the JWT `sub` (per-user buckets). Safe to read
    unverified here because these routes are behind get_current_user — a forged
    token gets its own bucket but still 401s, so it can't do damage. PUBLIC routes
    must use ip_key instead (see above)."""
    token = _session_token(request)
    if token:
        try:
            sub = jwt.get_unverified_claims(token).get("sub")
            if sub:
                # False positive: an internal rate-limit key, never rendered as
                # HTTP output; `sub` is a JWT-claim UUID. Suppress the Flask rule.
                return f"user:{sub}"  # nosemgrep
        except Exception:
            # Malformed token — fall through to IP keying.
            pass
    return ip_key(request)


limiter = Limiter(
    key_func=rate_key,
    default_limits=[settings.rate_limit_general],
    storage_uri=settings.redis_dsn() or "memory://",
    strategy="moving-window",
    headers_enabled=True,  # emit X-RateLimit-* and Retry-After
    swallow_errors=True,  # fail-open on storage errors
)

# Login throttle: fail-CLOSED (a Redis outage must NOT reopen the brute-force
# window) and keyed on IP only via ip_key. We PEEK before the attempt and consume
# a token only on FAILURE, so a burst of *successful* logins from one office NAT IP
# can't lock out staff, while repeated failures from an IP are throttled.
_login_storage = storage_from_string(settings.redis_dsn() or "memory://")
_login_strategy = MovingWindowRateLimiter(_login_storage)
_login_limit = parse(settings.rate_limit_auth)


def login_allowed(key: str) -> bool:
    """Whether this IP may attempt a login now — peek WITHOUT consuming. Fail-closed:
    a storage error denies rather than letting unlimited attempts through."""
    try:
        return _login_strategy.test(_login_limit, key)
    except Exception:
        return False


def register_login_failure(key: str) -> None:
    """Consume one token after a FAILED login. Best-effort — a storage error just
    means this failure isn't counted (the next peek still fails closed on outage)."""
    try:
        _login_strategy.hit(_login_limit, key)
    except Exception:
        pass
