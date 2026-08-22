from datetime import UTC, datetime
from html import escape as html_escape

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
from app.models import DeactivationRequest, User
from app.schemas.auth import (
    ChangePasswordRequest,
    DeactivationRequestCreate,
    DeactivationRequestOut,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MfaChallenge,
    MfaRecoverCompleteRequest,
    MfaRecoverStartRequest,
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
    IdentityResetIncomplete,
    InvalidCredentialsError,
    PasswordPolicyError,
    RateLimitedError,
    admin_recreate_user,
    change_password,
    complete_mfa_setup,
    confirm_forgot_password,
    forgot_password,
    global_sign_out,
    initiate_auth,
    password_challenge,
    respond_new_password,
    respond_software_token_mfa,
    start_mfa_setup,
)
from app.services.mailer import MailError, send_email
from app.services.provisioning import RESET_PENDING_PREFIX
from app.services.recovery_codes import issue_code, verify_code
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


_RECOVERY_SUBJECT = "Your Heimdall authenticator reset code"


def _recovery_email(code: str) -> tuple[str, str]:
    text = (
        "Hello,\n\nSomeone asked to reset the authenticator app on your Heimdall account. "
        f"Enter this code on the reset screen: {code}\n\nThe code expires in 10 minutes. "
        "If you didn't request this, you can ignore this email - nothing has changed. "
        "If you don't recognise the activity, contact your administrator.\n\n- Heimdall"
    )
    html = (
        "<p>Hello,</p><p>Someone asked to reset the authenticator app on your Heimdall account. "
        "Enter this code on the reset screen:</p>"
        f'<p style="font-size:20px;letter-spacing:4px"><strong>{code}</strong></p>'
        "<p>The code expires in 10 minutes. If you didn't request this, you can ignore this "
        "email &mdash; nothing has changed. If you don't recognise the activity, contact your "
        "administrator.</p><p>&mdash; Heimdall</p>"
    )
    return text, html


@router.post("/mfa/recover/start", status_code=status.HTTP_202_ACCEPTED)
async def mfa_recover_start(
    body: MfaRecoverStartRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Lost authenticator, step 1: prove the password, then we email a one-time
    code. The password check is the gate — an unknown email or wrong password is
    a plain 401 (same as login), and nothing is sent."""
    throttle_key = await _throttle(request)
    email = body.email.strip().lower()
    try:
        challenge = await run_in_threadpool(password_challenge, email, body.password)
    except InvalidCredentialsError:
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from None
    except (RateLimitedError, CognitoError) as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc
    if challenge != "SOFTWARE_TOKEN_MFA":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There's no authenticator on this account yet - just sign in to set one up.",
        )
    # Each start consumes an attempt: a correct password still shouldn't let
    # anyone flood a mailbox with codes.
    await run_in_threadpool(register_login_failure, throttle_key)
    code = await run_in_threadpool(issue_code, email)
    text, html = _recovery_email(code)
    try:
        await run_in_threadpool(
            send_email, to=email, subject=_RECOVERY_SUBJECT, text=text, html=html
        )
    except MailError as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We couldn't send the email right now. Please try again later.",
        ) from exc
    await log_audit(
        session,
        action="mfa_reset_requested",
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
        metadata={"email": email},  # password was verified, so the email is the user's
    )
    await session.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/mfa/recover/complete", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_recover_complete(
    body: MfaRecoverCompleteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Lost authenticator, step 2: password + emailed code -> the authenticator is
    removed (identity recreated, same password), every session is signed out, and
    the next login enrolls a new authenticator."""
    throttle_key = await _throttle(request)
    email = body.email.strip().lower()
    try:
        challenge = await run_in_threadpool(password_challenge, email, body.password)
    except InvalidCredentialsError:
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from None
    except (RateLimitedError, CognitoError) as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc
    if challenge != "SOFTWARE_TOKEN_MFA":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There's no authenticator on this account yet - just sign in to set one up.",
        )
    if not await run_in_threadpool(verify_code, email, body.code.strip()):
        await _record_auth_failure(session, request, throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That code didn't match, or it expired. Request a new one.",
        )

    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        # Cognito knows them but the app doesn't — nothing to rebind; refuse.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not provisioned. Contact your administrator.",
        )
    try:
        new_sub = await run_in_threadpool(admin_recreate_user, email, body.password)
    except IdentityResetIncomplete as exc:
        # The old identity is gone and the new one couldn't be finished. Mark the
        # row so an admin re-invite is allowed to rebind it (provisioning checks
        # for this prefix), audit it, and tell the user exactly what to do.
        user.cognito_sub = f"{RESET_PENDING_PREFIX}{user.cognito_sub}"
        user.sessions_revoked_at = datetime.now(UTC)
        user.session_keep_jti = None
        await log_audit(
            session,
            action="mfa_reset_failed",
            resource_type="user",
            resource_id=user.id,
            user_id=user.id,
            practice_id=user.practice_id,
            ip=safe_ip(client_ip(request)),
            user_agent=request.headers.get("user-agent"),
            metadata={"email": email, "error": str(exc)},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Your sign-in was reset but couldn't be re-created. "
                "Ask your administrator to send you a new invitation."
            ),
        ) from exc
    except (InvalidCredentialsError, RateLimitedError, CognitoError) as exc:
        await _record_auth_error(session, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc
    user.cognito_sub = new_sub
    user.sessions_revoked_at = datetime.now(UTC)
    user.session_keep_jti = None
    await log_audit(
        session,
        action="mfa_reset",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        practice_id=user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
        metadata={"email": email},
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
    """Sign out: clear the session cookie, revoke every app session (tokens are
    verified locally, so Cognito's sign-out alone can't end one already open),
    best-effort Cognito global sign-out (stops refresh), and an audit row."""
    token = request.cookies.get(AUTH_COOKIE) or (creds.credentials if creds else None)
    clear_auth_cookie(response)
    # Global by design: with one keep-slot there is no "this device only". A
    # token captured before sign-out must not outlive it.
    current_user.sessions_revoked_at = datetime.now(UTC)
    current_user.session_keep_jti = None
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


# --- Deactivation requests ----------------------------------------------------
# Accounts belong to the practice: a user can ASK to be deactivated, an admin
# decides (/api/admin/deactivation-requests). No self-service delete.


async def _pending_request(session: AsyncSession, user: User) -> DeactivationRequest | None:
    return await session.scalar(
        select(DeactivationRequest).where(
            DeactivationRequest.user_id == user.id, DeactivationRequest.status == "pending"
        )
    )


async def _notify_admins_of_request(session: AsyncSession, user: User, reason: str | None) -> None:
    """Best-effort email to every active admin. A mail failure never fails the
    request — admins also see it on the Users page."""
    admins = (
        (
            await session.execute(
                select(User.email).where(User.role == "admin", User.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    who = f"{user.full_name} ({user.email})" if user.full_name else user.email
    reason_line = f"Reason given: {reason}" if reason else "No reason given."
    text = (
        f"{who} has asked to have their Heimdall account deactivated.\n{reason_line}\n\n"
        f"Review it under Admin -> Users: https://heimdallclaims.com/admin/users\n\n- Heimdall"
    )
    # Name and reason are user-typed: escape them before they land in HTML.
    users_url = "https://heimdallclaims.com/admin/users"
    html = (
        f"<p><strong>{html_escape(who)}</strong> has asked to have their Heimdall "
        "account deactivated.</p>"
        f"<p>{html_escape(reason_line)}</p>"
        f'<p>Review it under <a href="{users_url}">Admin &rarr; Users</a>.</p>'
        "<p>&mdash; Heimdall</p>"
    )
    for admin_email in admins:
        try:
            await run_in_threadpool(
                send_email,
                to=admin_email,
                subject="Account deactivation request",
                text=text,
                html=html,
            )
        except MailError:
            pass  # logged by the mailer; the request itself still stands


@router.post(
    "/deactivation-request",
    response_model=DeactivationRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def request_deactivation(
    body: DeactivationRequestCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DeactivationRequest:
    reason = (body.reason or "").strip()[:500] or None
    # One open request per user is enforced by the partial unique index; insert
    # atomically against it rather than check-then-act, so a double submit is
    # a clean 409 instead of an IntegrityError at commit (same shape as
    # upsert_outcome).
    inserted = await session.scalar(
        pg_insert(DeactivationRequest)
        .values(user_id=current_user.id, practice_id=current_user.practice_id, reason=reason)
        .on_conflict_do_nothing(index_elements=["user_id"], index_where=text("status = 'pending'"))
        .returning(DeactivationRequest.id)
    )
    if inserted is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending request.",
        )
    req = await session.get(DeactivationRequest, inserted)
    await log_audit(
        session,
        action="deactivation_requested",
        resource_type="user",
        resource_id=current_user.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await _notify_admins_of_request(session, current_user, reason)
    return req


@router.get("/deactivation-request", response_model=DeactivationRequestOut | None)
async def my_deactivation_request(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DeactivationRequest | None:
    return await _pending_request(session, current_user)


@router.delete("/deactivation-request", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_deactivation_request(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Withdraw a pending request. Kept as a row (status denied, resolved by the
    requester) so the history stays complete."""
    req = await _pending_request(session, current_user)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending request")
    req.status = "denied"
    req.resolved_by = current_user.id
    req.resolved_at = datetime.now(UTC)
    await log_audit(
        session,
        action="deactivation_request_cancelled",
        resource_type="user",
        resource_id=current_user.id,
        user_id=current_user.id,
        practice_id=current_user.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
