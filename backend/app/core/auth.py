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
    global _jwks_by_kid
    if _jwks_by_kid is not None and not force_refresh:
        return _jwks_by_kid
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_JWKS_URL)
            resp.raise_for_status()
            _jwks_by_kid = {key["kid"]: key for key in resp.json()["keys"]}
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        # A transient Cognito/network blip shouldn't 500. Serve the stale cache if
        # we have one; otherwise ask the client to retry rather than fail hard.
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
        # Possible key rotation — refresh once before giving up.
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
    return user


def role_allowed(role: str | None, allowed: tuple[str, ...]) -> bool:
    """Whether a user's role is permitted. Pure, so it's unit-testable."""
    return role in allowed


def require_role(*allowed: str):
    """Dependency factory for role-gated endpoints, e.g.
    `Depends(require_role("admin"))`. Server-side RBAC — hiding a button is not
    security. Non-breaking: no existing route uses it; attach to new privileged
    routes as they are introduced (roles: doctor, office_manager, admin)."""

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if not role_allowed(user.role, allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dep
