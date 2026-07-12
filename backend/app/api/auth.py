from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user, security, verify_access_token
from app.core.net import client_ip
from app.core.rate_limit import ip_key, login_allowed, register_login_failure
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MfaChallenge,
    MfaSetupCompleteRequest,
    MfaSetupStartRequest,
    MfaSetupStartResponse,
    MfaVerifyRequest,
    UserOut,
)
from app.services.audit import log_audit, safe_ip
from app.services.cognito import (
    CognitoError,
    InvalidCredentialsError,
    complete_mfa_setup,
    global_sign_out,
    initiate_auth,
    respond_software_token_mfa,
    start_mfa_setup,
)
from app.services.users import link_user_on_login

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _throttle(request: Request) -> str:
    """Fail-closed, IP-keyed login throttle (peek only — failures counted separately)."""
    key = ip_key(request)
    if not await run_in_threadpool(login_allowed, key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
    return key


async def _record_auth_failure(session: AsyncSession, request: Request, throttle_key: str) -> None:
    # Count the failed attempt against the IP (successful logins don't consume). No
    # email in metadata — on a failed login it's attacker-supplied and would let
    # anyone flood the append-only audit table with arbitrary PII.
    await run_in_threadpool(register_login_failure, throttle_key)
    await log_audit(
        session,
        action="login_failure",
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()


async def _record_auth_error(session: AsyncSession, request: Request) -> None:
    await log_audit(
        session,
        action="login_error",
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()


async def _finalize_login(
    session: AsyncSession, request: Request, tokens: dict, email: str
) -> LoginResponse:
    """Shared tail for a completed auth (direct or post-MFA): trust-but-verify the
    token, link or deny the app account, audit, and return tokens."""
    ip = safe_ip(client_ip(request))
    user_agent = request.headers.get("user-agent")
    claims = await verify_access_token(tokens["AccessToken"])
    user = await link_user_on_login(session, cognito_sub=claims["sub"], email=email)
    if user is None:
        # Valid Cognito credentials but no provisioned app account — deny, never
        # auto-create (that would drop the login into an existing practice).
        await log_audit(
            session,
            action="login_denied",
            ip=ip,
            user_agent=user_agent,
            metadata={"email": email},
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
        metadata={"email": email},
    )
    await session.commit()
    return LoginResponse(
        access_token=tokens["AccessToken"],
        token_type=tokens.get("TokenType", "Bearer"),
        expires_in=tokens.get("ExpiresIn", 3600),
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    throttle_key = await _throttle(request)
    try:
        auth = await run_in_threadpool(initiate_auth, body.email, body.password)
    except InvalidCredentialsError:
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from None
    except CognitoError as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc

    # Password accepted but a TOTP challenge remains — return it (no tokens yet).
    if auth.challenge:
        return LoginResponse(mfa=MfaChallenge(challenge=auth.challenge, session=auth.session))
    return await _finalize_login(session, request, auth.tokens, body.email)


@router.post("/mfa/verify", response_model=LoginResponse)
async def mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Answer the SOFTWARE_TOKEN_MFA challenge (already-enrolled user)."""
    throttle_key = await _throttle(request)
    try:
        tokens = await run_in_threadpool(
            respond_software_token_mfa, body.email, body.session, body.code
        )
    except InvalidCredentialsError:
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="That code didn't match. Try again."
        ) from None
    except CognitoError as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc
    return await _finalize_login(session, request, tokens, body.email)


@router.post("/mfa/setup/start", response_model=MfaSetupStartResponse)
async def mfa_setup_start(body: MfaSetupStartRequest, request: Request) -> MfaSetupStartResponse:
    """Begin TOTP enrollment for the MFA_SETUP challenge — returns the shared secret
    (the client renders the authenticator QR) and a session to carry into complete."""
    await _throttle(request)
    try:
        out = await run_in_threadpool(start_mfa_setup, body.session)
    except (InvalidCredentialsError, CognitoError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Couldn't start authenticator setup. Please sign in again.",
        ) from exc
    return MfaSetupStartResponse(secret=out["secret"], session=out["session"])


@router.post("/mfa/setup/complete", response_model=LoginResponse)
async def mfa_setup_complete(
    body: MfaSetupCompleteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Verify the first TOTP code and finish enrollment (MFA_SETUP challenge)."""
    throttle_key = await _throttle(request)
    try:
        tokens = await run_in_threadpool(complete_mfa_setup, body.email, body.session, body.code)
    except InvalidCredentialsError:
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="That code didn't match. Try again."
        ) from None
    except CognitoError as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc
    return await _finalize_login(session, request, tokens, body.email)


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
