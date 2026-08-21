from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import (
    AUTH_COOKIE,
    clear_auth_cookie,
    get_current_user,
    security,
    set_auth_cookie,
    verify_access_token,
)
from app.core.net import client_ip
from app.core.rate_limit import ip_key, login_allowed, register_login_failure
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MfaChallenge,
    MfaSetupCompleteRequest,
    MfaSetupStartRequest,
    MfaSetupStartResponse,
    MfaVerifyRequest,
    ResetPasswordRequest,
    SetPasswordRequest,
    UserOut,
)
from app.services.audit import log_audit, safe_ip
from app.services.cognito import (
    CognitoError,
    InvalidCredentialsError,
    PasswordPolicyError,
    RateLimitedError,
    change_password,
    complete_mfa_setup,
    confirm_forgot_password,
    forgot_password,
    global_sign_out,
    initiate_auth,
    respond_new_password,
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
    session: AsyncSession, request: Request, response: Response, tokens: dict, email: str
) -> LoginResponse:
    """Shared tail for a completed auth (direct or post-MFA): trust-but-verify the
    token, link or deny the app account, audit, and set the httpOnly session cookie."""
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
    # Start the idle clock NOW. Without this the brand-new session inherits
    # whatever `last_seen_at` the PREVIOUS session left behind — so if the user
    # was last active more than IDLE_TIMEOUT_MINUTES ago (i.e. essentially always,
    # by the time someone comes back to log in), `get_current_user` expires the
    # session on the very first request after a successful login. Symptom:
    # /api/auth/login and /api/auth/mfa/verify both return 200, then /api/auth/me
    # immediately 401s and the user is bounced back to the login screen forever.
    user.last_seen_at = datetime.now(UTC)

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
    # The access token goes in an httpOnly cookie, NOT the JSON body — so it's never
    # readable by JavaScript (XSS-safe). The client just relies on the cookie.
    expires_in = tokens.get("ExpiresIn", 3600)
    set_auth_cookie(response, tokens["AccessToken"], max_age=expires_in)
    return LoginResponse(token_type=tokens.get("TokenType", "Bearer"), expires_in=expires_in)


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
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

    # Password accepted but a challenge remains (TOTP, or a forced password change
    # for a temporary password) — return it (no tokens yet).
    if auth.challenge:
        return LoginResponse(mfa=MfaChallenge(challenge=auth.challenge, session=auth.session))
    return await _finalize_login(session, request, response, auth.tokens, body.email)


@router.post("/password/set", response_model=LoginResponse)
async def password_set(
    body: SetPasswordRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Answer NEW_PASSWORD_REQUIRED: a user invited with a temporary password picks
    their own. Cognito usually chains straight into MFA_SETUP afterwards, so this
    returns the same shape as /login and the client branches the same way."""
    throttle_key = await _throttle(request)
    try:
        auth = await run_in_threadpool(
            respond_new_password, body.email, body.session, body.new_password
        )
    except PasswordPolicyError as exc:
        raise _password_policy_400(exc) from None
    except InvalidCredentialsError:
        # Stale/expired session (Cognito sessions last ~3 minutes) or a bad request.
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your sign-in session expired. Please sign in again.",
        ) from None
    except CognitoError as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc

    await log_audit(
        session,
        action="password_set",
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    if auth.challenge:
        return LoginResponse(mfa=MfaChallenge(challenge=auth.challenge, session=auth.session))
    return await _finalize_login(session, request, response, auth.tokens, body.email)


def _password_policy_400(exc: PasswordPolicyError) -> HTTPException:
    # Cognito's own policy text (e.g. "Password must have symbol characters") —
    # never the password itself — is the most useful thing to show the user.
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Password doesn't meet the requirements: {exc}",
    )


_TOO_MANY = HTTPException(
    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    detail="Too many attempts. Please wait a while and try again.",
)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def password_forgot(
    body: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Start a self-service reset: Cognito emails a code to the account's address.

    Always 202, whatever Cognito said about the account — an unknown address, a
    not-yet-activated invite, and a real send are indistinguishable to the caller,
    so this endpoint can't be used to enumerate users. Each call consumes a login
    attempt from the IP's budget, because each one can trigger an email.
    """
    throttle_key = await _throttle(request)
    await run_in_threadpool(register_login_failure, throttle_key)
    try:
        await run_in_threadpool(forgot_password, body.email)
    except (InvalidCredentialsError, RateLimitedError):
        pass  # deliberately indistinguishable from success
    except CognitoError as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc
    # No email in metadata: it's caller-supplied and unverified at this point.
    await log_audit(
        session,
        action="password_reset_requested",
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def password_reset(
    body: ResetPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Finish a self-service reset with the emailed code. The user then signs in
    normally (password + their existing authenticator)."""
    throttle_key = await _throttle(request)
    try:
        await run_in_threadpool(confirm_forgot_password, body.email, body.code, body.new_password)
    except PasswordPolicyError as exc:
        raise _password_policy_400(exc) from None
    except InvalidCredentialsError:
        # Wrong/expired code — or an unknown user, which must look the same.
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That code didn't match, or it expired. Request a new one.",
        ) from None
    except RateLimitedError:
        raise _TOO_MANY from None
    except CognitoError as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc
    # Cognito accepted the code for this email, so it's verified. Sign the account
    # out everywhere: a reset is most often "someone else might have my password".
    user = await session.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is not None:
        user.sessions_revoked_at = datetime.now(UTC)
        user.session_keep_jti = None
    await log_audit(
        session,
        action="password_reset",
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
        metadata={"email": body.email},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
async def password_change(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Signed-in password change. Cognito re-checks the current password against
    the caller's own access token, so one user can never change another's."""
    throttle_key = await _throttle(request)
    token = request.cookies.get(AUTH_COOKIE) or (creds.credentials if creds else None)
    try:
        await run_in_threadpool(change_password, token, body.current_password, body.new_password)
    except PasswordPolicyError as exc:
        raise _password_policy_400(exc) from None
    except InvalidCredentialsError:
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your current password didn't match.",
        ) from None
    except RateLimitedError:
        raise _TOO_MANY from None
    except CognitoError as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc
    # Sign out every OTHER session: tokens issued before now are refused, except
    # this one (matched by jti), so the user stays in the tab they're using.
    claims = await verify_access_token(token)
    current_user.sessions_revoked_at = datetime.now(UTC)
    current_user.session_keep_jti = claims.get("jti")
    await log_audit(
        session,
        action="password_change",
        resource_type="user",
        resource_id=current_user.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/mfa/verify", response_model=LoginResponse)
async def mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    response: Response,
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
    return await _finalize_login(session, request, response, tokens, body.email)


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
    response: Response,
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
    return await _finalize_login(session, request, response, tokens, body.email)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Sign out: clear the session cookie + best-effort Cognito global sign-out
    (revokes refresh tokens so the session can't be renewed) + an audit row."""
    token = request.cookies.get(AUTH_COOKIE) or (creds.credentials if creds else None)
    clear_auth_cookie(response)
    if token:
        try:
            await run_in_threadpool(global_sign_out, token)
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


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat(current_user: User = Depends(get_current_user)) -> Response:
    """Report that a human is still here.

    Deliberately does nothing: the whole effect is the `last_seen_at` stamp that
    `get_current_user` writes for any non-polling path, which refreshes the idle
    clock. The frontend calls this only on real interaction (mouse, key, scroll,
    touch), throttled to once a minute — so reading a long letter keeps you
    signed in, while an unattended tab does not.

    It cannot be used to extend a session that has ALREADY gone idle: the
    dependency evaluates the timeout before the stamp, so a stale session gets
    401 here exactly as it would anywhere else.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)
