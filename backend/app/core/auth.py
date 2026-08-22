import asyncio
import re
import time
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import User

# Auth token lives in an httpOnly cookie (XSS-safe): JS can't read it, the browser
# sends it automatically. Same-site (api.heimdallclaims.com <-> heimdallclaims.com)
# so SameSite=Lax works and PHI never transits the frontend host.
AUTH_COOKIE = "hd_session"

# How stale `last_seen_at` may get before we write it again. The case-status poll
# runs every 2 seconds, so stamping on every request would make one UPDATE per
# poll per user. A minute of granularity is far finer than the 15-minute idle
# window it feeds, so the enforcement is unaffected.
_LAST_SEEN_WRITE_INTERVAL = timedelta(minutes=1)


def set_auth_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.app_env == "production",  # ALB serves HTTPS to the browser
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE,
        path="/",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )


_ISSUER = (
    f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
    f"{settings.cognito_user_pool_id}"
)
_JWKS_URL = f"{_ISSUER}/.well-known/jwks.json"

# Cognito's signing keys are stable and small; cache them by kid after first use.
_jwks_by_kid: dict[str, dict] | None = None
# A forced refresh is triggered by an UNVERIFIED header's `kid`, so an attacker
# can request one per call. Bound it: at most one refetch per window, and
# concurrent misses coalesce behind one lock instead of each fetching.
_JWKS_REFRESH_MIN_INTERVAL = 60.0
_jwks_last_refresh: float = 0.0
_jwks_lock = asyncio.Lock()

# auto_error=False so a MISSING header yields our 401 (+ WWW-Authenticate) rather
# than HTTPBearer's default 403 — the frontend maps only 401 to the sign-in flow.
security = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Invalid or expired token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _get_jwks(force_refresh: bool = False) -> dict[str, dict]:
    global _jwks_by_kid, _jwks_last_refresh
    if _jwks_by_kid is not None and not force_refresh:
        return _jwks_by_kid
    async with _jwks_lock:
        # Re-check under the lock: a concurrent caller may have just refreshed.
        now = time.monotonic()
        if _jwks_by_kid is not None and (
            not force_refresh or now - _jwks_last_refresh < _JWKS_REFRESH_MIN_INTERVAL
        ):
            return _jwks_by_kid
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_JWKS_URL)
                resp.raise_for_status()
                _jwks_by_kid = {key["kid"]: key for key in resp.json()["keys"]}
                _jwks_last_refresh = now
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            # A transient Cognito/network blip shouldn't 500. Serve the stale
            # cache if we have one; otherwise ask the client to retry.
            if _jwks_by_kid is not None:
                return _jwks_by_kid
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication key service temporarily unavailable",
                headers={"Retry-After": "5"},
            ) from exc
        return _jwks_by_kid


async def verify_access_token(token: str) -> dict:
    """Verify a Cognito *access* token (RS256) and return its claims.

    Access tokens carry `client_id` (not `aud`) and `token_use=access`, both of
    which we check explicitly in addition to signature, issuer, and expiry.
    """
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except JWTError as exc:
        raise _unauthorized() from exc

    jwks = await _get_jwks()
    key = jwks.get(kid)
    if key is None:
        # Possible key rotation — refresh (rate-bounded) before giving up.
        jwks = await _get_jwks(force_refresh=True)
        key = jwks.get(kid)
        if key is None:
            raise _unauthorized()

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=_ISSUER,
            options={"verify_aud": False},  # access tokens have no `aud`
        )
    except JWTError as exc:
        raise _unauthorized() from exc

    if claims.get("token_use") != "access":
        raise _unauthorized("Wrong token type")
    if claims.get("client_id") != settings.cognito_client_id:
        raise _unauthorized("Token not issued for this client")
    return claims


def _idle_deadline_exceeded(last_seen: datetime | None) -> bool:
    """Whether this session has been idle past the configured window.

    Enforced HERE, server-side. The frontend's 15-minute `setTimeout` is a UX
    affordance, not a control: closing the tab at minute 1 cancels the timer and
    leaves the session valid for the token's full remaining life (~59 more
    minutes). §164.312(a)(2)(iii) automatic logoff needs a server that refuses the
    stale session, not a browser that intends to.
    """
    if settings.idle_timeout_minutes <= 0 or last_seen is None:
        return False
    idle_for = datetime.now(UTC) - last_seen
    return idle_for > timedelta(minutes=settings.idle_timeout_minutes)


# Requests the app makes on a timer, with nobody necessarily at the keyboard.
# These must NOT refresh the idle clock, or the timeout is defeated by the
# product's own background traffic: ReadyNotifier polls processing-ids every 12s
# with refetchIntervalInBackground, and the case page polls status every 2s while
# a pipeline runs. An open tab would then hold a session alive indefinitely — the
# exact failure §164.312(a)(2)(iii) exists to prevent.
#
# Genuine interaction reaches the server either as a real API call or, when the
# user is only reading, as the explicit heartbeat from `use-idle-logout.ts`.
_POLL_PATHS = re.compile(
    r"^/api/cases/processing-ids/?$" r"|^/api/cases/[0-9a-fA-F-]{36}/status/?$"
)


def is_user_activity(path: str) -> bool:
    """Whether a request path should count as the user being present. Pure, so
    the classification is unit-testable without a request or a database."""
    return not _POLL_PATHS.match(path)


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db),
) -> User:
    # Cookie first (browser sessions), then Authorization header (API clients).
    token = request.cookies.get(AUTH_COOKIE) or (creds.credentials if creds else None)
    if not token:
        raise _unauthorized("Missing bearer token")
    claims = await verify_access_token(token)
    user = await session.scalar(select(User).where(User.cognito_sub == claims["sub"]))
    if user is None:
        raise _unauthorized("User is not provisioned")

    # Kill switch. Cognito access tokens cannot be revoked — only refresh tokens
    # can — so without a server-side check an admin who learns an account is
    # compromised has no supported lever at all, and the token stays good for its
    # full 60-minute life. The users row cannot be deleted instead, because
    # audit_logs.user_id is ON DELETE RESTRICT.
    if not user.is_active:
        raise _unauthorized("Account is deactivated")

    if session_revoked(claims, user.sessions_revoked_at, user.session_keep_jti):
        raise _unauthorized("Session was signed out")

    if _idle_deadline_exceeded(user.last_seen_at):
        raise _unauthorized("Session expired due to inactivity")

    # Sliding activity stamp — but ONLY for requests that imply a human. Polling
    # endpoints are excluded (see _POLL_PATHS), so leaving the app open on screen
    # no longer keeps the session alive; walking away expires it on schedule even
    # with the tab in front of you.
    #
    # The write is throttled so an active user costs at most one UPDATE a minute,
    # which is far finer than the 15-minute window it feeds.
    if is_user_activity(request.url.path):
        now = datetime.now(UTC)
        if user.last_seen_at is None or (now - user.last_seen_at) > _LAST_SEEN_WRITE_INTERVAL:
            user.last_seen_at = now
            await session.commit()
    return user


def session_revoked(claims: dict, revoked_at: datetime | None, keep_jti: str | None) -> bool:
    """Whether this token predates a revocation (password change/reset, admin
    deactivation) and isn't the one session allowed to survive it. Pure, so the
    boundary cases are unit-testable. A token with no iat is treated as revoked
    once any revocation exists — fail closed."""
    if revoked_at is None:
        return False
    if keep_jti is not None and claims.get("jti") == keep_jti:
        return False
    iat = claims.get("iat")
    if iat is None:
        return True
    # iat has one-second resolution; treat the token as issued at the END of its
    # second so a login landing in the same second as the revocation isn't
    # refused. A one-second grace is immaterial; a false lockout is not.
    return datetime.fromtimestamp(iat + 1, tz=UTC) <= revoked_at


def role_allowed(role: str | None, allowed: tuple[str, ...]) -> bool:
    """Whether a user's role is permitted. Pure, so it's unit-testable."""
    return role in allowed


def require_role(*allowed: str):
    """Dependency factory for role-gated endpoints, e.g.
    `Depends(require_role("admin"))`. Server-side RBAC — hiding a button is not
    security. Used by api/admin.py and api/admin_users.py; attach it to any new
    privileged route (roles: doctor, office_manager, admin)."""

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if not role_allowed(user.role, allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dep
