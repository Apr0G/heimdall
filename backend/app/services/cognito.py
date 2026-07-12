from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

# Cognito challenges we handle in the login flow (TOTP MFA).
_MFA_CHALLENGES = ("SOFTWARE_TOKEN_MFA", "MFA_SETUP")
# Cognito error codes that mean "the secret/code the user supplied was wrong".
_BAD_CREDENTIAL_CODES = {
    "NotAuthorizedException",
    "UserNotFoundException",
    "UserNotConfirmedException",
    "CodeMismatchException",
    "ExpiredCodeException",
}


class InvalidCredentialsError(Exception):
    """Email/password (or MFA code) rejected by Cognito."""


class CognitoError(Exception):
    """Any other Cognito failure (service error, unexpected challenge)."""


@dataclass
class AuthResult:
    """Outcome of a login step: either tokens (done) or an MFA challenge to answer."""

    tokens: dict | None = None
    challenge: str | None = None  # "SOFTWARE_TOKEN_MFA" | "MFA_SETUP"
    session: str | None = None  # opaque Cognito session carried to the next step


def _client_error(exc: ClientError) -> Exception:
    code = exc.response.get("Error", {}).get("Code", "")
    if code in _BAD_CREDENTIAL_CODES:
        return InvalidCredentialsError(code)
    return CognitoError(code)


_client = None


def _get_client():
    # Lazily created so importing this module never requires AWS connectivity.
    global _client
    if _client is None:
        _client = boto3.client("cognito-idp", region_name=settings.cognito_region)
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
    except ClientError as exc:
        raise _client_error(exc) from exc

    result = resp.get("AuthenticationResult")
    if result is not None:
        return AuthResult(tokens=result)
    challenge = resp.get("ChallengeName")
    if challenge in _MFA_CHALLENGES:
        return AuthResult(challenge=challenge, session=resp["Session"])
    # Any other challenge (e.g. NEW_PASSWORD_REQUIRED) is unsupported.
    raise CognitoError(challenge or "no_authentication_result")


def respond_software_token_mfa(email: str, session: str, code: str) -> dict:
    """Answer the SOFTWARE_TOKEN_MFA challenge with a TOTP code; return tokens."""
    try:
        resp = _get_client().respond_to_auth_challenge(
            ClientId=settings.cognito_client_id,
            ChallengeName="SOFTWARE_TOKEN_MFA",
            Session=session,
            ChallengeResponses={"USERNAME": email, "SOFTWARE_TOKEN_MFA_CODE": code},
        )
    except ClientError as exc:
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
    except ClientError as exc:
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
    except ClientError as exc:
        raise _client_error(exc) from exc
    result = resp.get("AuthenticationResult")
    if result is None:
        raise CognitoError("mfa_setup_no_result")
    return result


def global_sign_out(access_token: str) -> None:
    """Revoke the user's refresh tokens across devices (Cognito GlobalSignOut).

    Access tokens remain valid until they expire (~1h) — Cognito cannot revoke an
    already-issued access token — so this stops session *renewal*, not the current
    token. Synchronous (boto3); call via a threadpool.
    """
    try:
        _get_client().global_sign_out(AccessToken=access_token)
    except ClientError as exc:
        raise CognitoError(exc.response.get("Error", {}).get("Code", "")) from exc
