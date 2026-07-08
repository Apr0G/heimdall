from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user, security, verify_access_token
from app.core.net import client_ip
from app.core.rate_limit import login_rate_ok, rate_key
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, UserOut
from app.services.audit import log_audit, safe_ip
from app.services.cognito import (
    CognitoError,
    InvalidCredentialsError,
    global_sign_out,
    initiate_auth,
)
from app.services.users import link_user_on_login

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    # Fail-closed login throttle — a Redis outage must not reopen brute-force.
    if not await run_in_threadpool(login_rate_ok, rate_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
    ip = safe_ip(client_ip(request))
    user_agent = request.headers.get("user-agent")

    try:
        auth = await run_in_threadpool(initiate_auth, body.email, body.password)
    except InvalidCredentialsError:
        # No email in metadata: on a failed login it's attacker-supplied and would
        # let anyone flood the append-only audit table with arbitrary PII.
        await log_audit(
            session,
            action="login_failure",
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from None
    except CognitoError as exc:
        await log_audit(
            session,
            action="login_error",
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc

    # Trust-but-verify: confirm the access token validates, and use its sub.
    claims = await verify_access_token(auth["AccessToken"])
    user = await link_user_on_login(session, cognito_sub=claims["sub"], email=body.email)
    if user is None:
        # Valid Cognito credentials but no provisioned app account — deny, never
        # auto-create (that would drop the login into an existing practice).
        await log_audit(
            session,
            action="login_denied",
            ip=ip,
            user_agent=user_agent,
            metadata={"email": body.email},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not provisioned. Contact your administrator.",
        )
    await log_audit(
        session,
        action="login_success",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        practice_id=user.practice_id,
        ip=ip,
        user_agent=user_agent,
        metadata={"email": body.email},
    )
    await session.commit()

    return LoginResponse(
        access_token=auth["AccessToken"],
        id_token=auth["IdToken"],
        token_type=auth.get("TokenType", "Bearer"),
        expires_in=auth.get("ExpiresIn", 3600),
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    creds: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Sign out server-side: best-effort Cognito global sign-out (revokes refresh
    tokens so the session can't be renewed) plus an audit row. The client clears
    its own token regardless of the Cognito result."""
    try:
        await run_in_threadpool(global_sign_out, creds.credentials)
    except CognitoError:
        pass  # never block the user's sign-out on a Cognito hiccup
    await log_audit(
        session,
        action="logout",
        resource_type="user",
        resource_id=current_user.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return {"detail": "signed out"}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
