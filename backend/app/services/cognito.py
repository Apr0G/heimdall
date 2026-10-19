import time
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, ParamValidationError

from app.core.config import settings

# Cognito challenges we handle in the login flow: TOTP MFA, plus the forced
# password change a freshly-invited user (temporary password) must complete first.
_MFA_CHALLENGES = ("SOFTWARE_TOKEN_MFA", "MFA_SETUP")
NEW_PASSWORD_CHALLENGE = "NEW_PASSWORD_REQUIRED"
_HANDLED_CHALLENGES = (*_MFA_CHALLENGES, NEW_PASSWORD_CHALLENGE)
# Cognito error codes that mean "the secret/code the user supplied was wrong".
_BAD_CREDENTIAL_CODES = {
    "NotAuthorizedException",
    "UserNotFoundException",
    "UserNotConfirmedException",
    "CodeMismatchException",
    "ExpiredCodeException",
    # VerifySoftwareToken (MFA enrollment) rejects a wrong first TOTP code with
    # THIS, not CodeMismatchException — without it a mistyped code during setup
    # surfaced as a generic 5xx ("something went wrong") instead of 401.
    "EnableSoftwareTokenMFAException",
}


class InvalidCredentialsError(Exception):
    """Email/password (or MFA code) rejected by Cognito."""


class PasswordPolicyError(Exception):
    """A chosen password was rejected by the pool's password policy. The message
    is Cognito's own (policy text only, never the password) — safe to show."""


class RateLimitedError(Exception):
    """Cognito's own per-user limit on codes/attempts (LimitExceededException)."""


class CognitoError(Exception):
    """Any other Cognito failure (service error, unexpected challenge)."""


class IdentityResetIncomplete(CognitoError):
    """admin_recreate_user deleted the old identity but could not finish the
    replacement after retries. The account needs an admin re-invite; the
    caller marks the users row so the next invite may rebind it."""


@dataclass
class AuthResult:
    """Outcome of a login step: either tokens (done) or an MFA challenge to answer."""

    tokens: dict | None = None
    challenge: str | None = None  # "SOFTWARE_TOKEN_MFA" | "MFA_SETUP" | "NEW_PASSWORD_REQUIRED"
    session: str | None = None  # opaque Cognito session carried to the next step


def _client_error(exc: Exception) -> Exception:
    # Malformed params (e.g. a too-short or stale session) — surface as a bad
    # credential so the client is told to retry/re-auth, never as a 500.
    if isinstance(exc, ParamValidationError):
        return InvalidCredentialsError("bad_request")
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in _BAD_CREDENTIAL_CODES:
            return InvalidCredentialsError(code)
        if code == "InvalidPasswordException":
            return PasswordPolicyError(exc.response.get("Error", {}).get("Message", ""))
        if code in ("LimitExceededException", "TooManyRequestsException"):
            return RateLimitedError(code)
        return CognitoError(code)
    return CognitoError(type(exc).__name__)  # other BotoCoreError (e.g. connection)


_client = None


def _get_client():
    # Lazily created so importing this module never requires AWS connectivity.
    global _client
    if _client is None:
        # Explicit, TIGHT timeouts: these calls sit directly in the login path, so
        # unbounded Cognito latency becomes unbounded login latency for every user.
        # Auth payloads are tiny, hence the much shorter read_timeout than S3's.
        _client = boto3.client(
            "cognito-idp",
            region_name=settings.cognito_region,
            config=Config(
                connect_timeout=5,
                read_timeout=15,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
    return _client


def initiate_auth(email: str, password: str) -> AuthResult:
    """Run the Cognito USER_PASSWORD_AUTH flow. Returns tokens, or a TOTP MFA
    challenge to answer next. Synchronous (boto3); call via a threadpool."""
    try:
        resp = _get_client().initiate_auth(
            ClientId=settings.cognito_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc

    return _auth_result(resp)


def _auth_result(resp: dict) -> AuthResult:
    result = resp.get("AuthenticationResult")
    if result is not None:
        return AuthResult(tokens=result)
    challenge = resp.get("ChallengeName")
    if challenge in _HANDLED_CHALLENGES:
        return AuthResult(challenge=challenge, session=resp["Session"])
    # Any other challenge (e.g. SMS_MFA, CUSTOM_CHALLENGE) is unsupported.
    raise CognitoError(challenge or "no_authentication_result")


def respond_new_password(email: str, session: str, new_password: str) -> AuthResult:
    """Answer NEW_PASSWORD_REQUIRED (first login with a temporary password). Cognito
    may then issue tokens OR chain straight into an MFA challenge — for a brand-new
    user on an MFA-required pool it is always MFA_SETUP — so the result has the same
    shape as initiate_auth and the caller branches identically."""
    try:
        resp = _get_client().respond_to_auth_challenge(
            ClientId=settings.cognito_client_id,
            ChallengeName=NEW_PASSWORD_CHALLENGE,
            Session=session,
            ChallengeResponses={"USERNAME": email, "NEW_PASSWORD": new_password},
        )
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc
    return _auth_result(resp)


def respond_software_token_mfa(email: str, session: str, code: str) -> dict:
    """Answer the SOFTWARE_TOKEN_MFA challenge with a TOTP code; return tokens."""
    try:
        resp = _get_client().respond_to_auth_challenge(
            ClientId=settings.cognito_client_id,
            ChallengeName="SOFTWARE_TOKEN_MFA",
            Session=session,
            ChallengeResponses={"USERNAME": email, "SOFTWARE_TOKEN_MFA_CODE": code},
        )
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc
    result = resp.get("AuthenticationResult")
    if result is None:
        raise CognitoError("mfa_no_result")
    return result


def start_mfa_setup(session: str) -> dict:
    """Begin TOTP enrollment (MFA_SETUP challenge): return the shared secret for the
    authenticator QR and a fresh session to carry into verification."""
    try:
        resp = _get_client().associate_software_token(Session=session)
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc
    return {"secret": resp["SecretCode"], "session": resp["Session"]}


def complete_mfa_setup(email: str, session: str, code: str) -> dict:
    """Verify the first TOTP code, then finish the MFA_SETUP challenge; return tokens."""
    try:
        verified = _get_client().verify_software_token(Session=session, UserCode=code)
        if verified.get("Status") != "SUCCESS":
            raise InvalidCredentialsError("mfa_verify_failed")
        resp = _get_client().respond_to_auth_challenge(
            ClientId=settings.cognito_client_id,
            ChallengeName="MFA_SETUP",
            Session=verified["Session"],
            ChallengeResponses={"USERNAME": email},
        )
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc
    result = resp.get("AuthenticationResult")
    if result is None:
        raise CognitoError("mfa_setup_no_result")
    return result


def password_challenge(email: str, password: str) -> str:
    """Check a password WITHOUT completing a login: run InitiateAuth and return the
    challenge Cognito raises next ("SOFTWARE_TOKEN_MFA" = password right and an
    authenticator is enrolled; "MFA_SETUP" = password right, nothing enrolled).
    Raises InvalidCredentialsError for a wrong password."""
    auth = initiate_auth(email, password)
    if auth.challenge is None:
        # MFA is required on the pool, so tokens here would mean misconfiguration.
        raise CognitoError("no_mfa_challenge")
    return auth.challenge


def admin_recreate_user(email: str, password: str) -> str:
    """Authenticator reset. Cognito offers no way to drop a user's TOTP device
    while the pool requires MFA (verified empirically: disabling the preference
    still yields SOFTWARE_TOKEN_MFA, and the challenge session can't associate a
    new token), so the identity is recreated: same email, same password, no
    authenticator — the next login runs the normal MFA_SETUP enrollment. Returns
    the NEW sub; the caller rebinds the users row. Only call after the person
    has proven both the password and control of the mailbox."""
    client = _get_client()
    try:
        client.admin_delete_user(UserPoolId=settings.cognito_user_pool_id, Username=email)
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc

    # Past this point the old identity is gone. The remaining two calls are
    # idempotent for our purposes (re-creating an existing user is the one
    # failure we can recognise and continue through), so retry them rather
    # than leave the account half-built on a transient throttle.
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            try:
                resp = client.admin_create_user(
                    UserPoolId=settings.cognito_user_pool_id,
                    Username=email,
                    MessageAction="SUPPRESS",  # no invite email — they keep their password
                    UserAttributes=[
                        {"Name": "email", "Value": email},
                        {"Name": "email_verified", "Value": "true"},
                    ],
                )
                sub = {a["Name"]: a["Value"] for a in resp["User"]["Attributes"]}["sub"]
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "UsernameExistsException":
                    raise
                # Created on a previous attempt whose response we lost.
                sub = client.admin_get_user(
                    UserPoolId=settings.cognito_user_pool_id, Username=email
                )["UserAttributes"]
                sub = {a["Name"]: a["Value"] for a in sub}["sub"]
            client.admin_set_user_password(
                UserPoolId=settings.cognito_user_pool_id,
                Username=email,
                Password=password,
                Permanent=True,
            )
            return sub
        except (ClientError, BotoCoreError) as exc:
            last_exc = exc
            time.sleep(0.5 * (attempt + 1))
    raise IdentityResetIncomplete(type(last_exc).__name__) from last_exc


def forgot_password(email: str) -> None:
    """Ask Cognito to email a reset code. Raises InvalidCredentialsError for an
    unknown/unresettable user — the CALLER must swallow that so the response never
    reveals whether an account exists."""
    try:
        _get_client().forgot_password(ClientId=settings.cognito_client_id, Username=email)
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc


def confirm_forgot_password(email: str, code: str, new_password: str) -> None:
    """Finish a reset: the emailed code + the new password."""
    try:
        _get_client().confirm_forgot_password(
            ClientId=settings.cognito_client_id,
            Username=email,
            ConfirmationCode=code,
            Password=new_password,
        )
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc


def change_password(access_token: str, current_password: str, new_password: str) -> None:
    """Signed-in password change; Cognito re-verifies the current password."""
    try:
        _get_client().change_password(
            AccessToken=access_token,
            PreviousPassword=current_password,
            ProposedPassword=new_password,
        )
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc


# --- Admin-side operations (IAM-authenticated; the app role holds these rights,
# gated in the API by require_role("admin") + an audit row per call). ----------


def admin_invite(email: str) -> tuple[str, bool]:
    """Create a Cognito user with an emailed temporary password, or re-send the
    invite if they already exist. Returns (sub, created). The password is
    generated by Cognito and only ever lands in the recipient's inbox."""
    common = {
        "UserPoolId": settings.cognito_user_pool_id,
        "Username": email,
        "DesiredDeliveryMediums": ["EMAIL"],
    }
    try:
        try:
            resp = _get_client().admin_create_user(
                **common,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    # An admin vetted the address; don't make the user confirm it.
                    {"Name": "email_verified", "Value": "true"},
                ],
            )
            created = True
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "UsernameExistsException":
                raise
            # RESEND only applies while the invite is unused (FORCE_CHANGE_PASSWORD);
            # Cognito rejects it otherwise and the caller reports that.
            resp = _get_client().admin_create_user(**common, MessageAction="RESEND")
            created = False
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc
    attrs = {a["Name"]: a["Value"] for a in resp["User"]["Attributes"]}
    return attrs["sub"], created


def admin_find_sub(email: str) -> str | None:
    """The `sub` of the Cognito user with this email, or None when no such user
    exists. Read-only — the provisioning flow uses it to refuse a rebind BEFORE
    admin_invite would create an identity or send an email."""
    try:
        resp = _get_client().admin_get_user(
            UserPoolId=settings.cognito_user_pool_id, Username=email
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "UserNotFoundException":
            return None
        raise _client_error(exc) from exc
    except BotoCoreError as exc:
        raise _client_error(exc) from exc
    attrs = {a["Name"]: a["Value"] for a in resp.get("UserAttributes", [])}
    return attrs.get("sub")


def admin_set_enabled(email: str, enabled: bool) -> None:
    """Disable (or re-enable) the Cognito account. Disabled users can't sign in or
    refresh; disabling also signs them out of Cognito everywhere."""
    client = _get_client()
    try:
        if enabled:
            client.admin_enable_user(UserPoolId=settings.cognito_user_pool_id, Username=email)
        else:
            client.admin_disable_user(UserPoolId=settings.cognito_user_pool_id, Username=email)
            client.admin_user_global_sign_out(
                UserPoolId=settings.cognito_user_pool_id, Username=email
            )
    except (ClientError, BotoCoreError) as exc:
        raise _client_error(exc) from exc


def global_sign_out(access_token: str) -> None:
    """Revoke the user's refresh tokens across devices (Cognito GlobalSignOut).

    Access tokens remain valid until they expire (~1h) — Cognito cannot revoke an
    already-issued access token — so this stops session *renewal*, not the current
    token. Synchronous (boto3); call via a threadpool.
    """
    try:
        _get_client().global_sign_out(AccessToken=access_token)
    except (ClientError, BotoCoreError) as exc:
        # Always CognitoError so the caller (logout) swallows it; guard .response
        # since a BotoCoreError has none.
        code = exc.response.get("Error", {}).get("Code", "") if isinstance(exc, ClientError) else ""
        raise CognitoError(code) from exc
