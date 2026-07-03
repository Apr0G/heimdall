import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import User

_ISSUER = (
    f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
    f"{settings.cognito_user_pool_id}"
)
_JWKS_URL = f"{_ISSUER}/.well-known/jwks.json"

# Cognito's signing keys are stable and small; cache them by kid after first use.
_jwks_by_kid: dict[str, dict] | None = None

security = HTTPBearer()


def _unauthorized(detail: str = "Invalid or expired token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _get_jwks(force_refresh: bool = False) -> dict[str, dict]:
    global _jwks_by_kid
    if _jwks_by_kid is None or force_refresh:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_JWKS_URL)
            resp.raise_for_status()
            _jwks_by_kid = {key["kid"]: key for key in resp.json()["keys"]}
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
    creds: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db),
) -> User:
    claims = await verify_access_token(creds.credentials)
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
