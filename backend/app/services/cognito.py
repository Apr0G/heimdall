import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


class InvalidCredentialsError(Exception):
    """Email/password rejected by Cognito (bad creds, unknown user, disabled)."""


class CognitoError(Exception):
    """Any other Cognito failure (service error, unexpected challenge)."""


_client = None


def _get_client():
    # Lazily created so importing this module never requires AWS connectivity.
    global _client
    if _client is None:
        _client = boto3.client("cognito-idp", region_name=settings.cognito_region)
    return _client


def initiate_auth(email: str, password: str) -> dict:
    """Run the Cognito USER_PASSWORD_AUTH flow and return the AuthenticationResult.

    Synchronous (boto3); call via a threadpool from async request handlers.
    """
    try:
        resp = _get_client().initiate_auth(
            ClientId=settings.cognito_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {
            "NotAuthorizedException",
            "UserNotFoundException",
            "UserNotConfirmedException",
        }:
            raise InvalidCredentialsError(code) from exc
        raise CognitoError(code) from exc

    # A challenge (e.g. NEW_PASSWORD_REQUIRED) means no tokens were issued. The
    # MVP login does not handle challenges, so surface it as an error.
    result = resp.get("AuthenticationResult")
    if result is None:
        raise CognitoError(resp.get("ChallengeName", "no_authentication_result"))
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
