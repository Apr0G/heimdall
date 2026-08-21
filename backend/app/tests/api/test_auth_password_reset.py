"""HTTP contract of the self-service reset (/password/forgot, /password/reset) and
the signed-in change (/password/change). Cognito and the DB helpers are stubbed.

The properties pinned here are security properties: the forgot endpoint must be
indistinguishable for known and unknown accounts, every path must count against
the IP throttle where it should, and no password ever appears in a response.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.main import app
from app.services.cognito import (
    CognitoError,
    InvalidCredentialsError,
    PasswordPolicyError,
    RateLimitedError,
)

client = TestClient(app)
NEW_PW = "Correct-Horse-9!"


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    monkeypatch.setattr(auth_api, "login_allowed", lambda key: True)
    monkeypatch.setattr(auth_api, "register_login_failure", MagicMock())
    monkeypatch.setattr(auth_api, "log_audit", AsyncMock())

    class _Session:
        # The reset path looks the user up by email to revoke their sessions.
        found_user = MagicMock(sessions_revoked_at=None, session_keep_jti="old")

        async def scalar(self, stmt):
            return self.found_user

        async def commit(self):
            pass

    monkeypatch.setattr(
        auth_api, "verify_access_token", AsyncMock(return_value={"jti": "this-jti"})
    )
    _stub_side_effects.session = _Session()

    async def _db():
        yield _stub_side_effects.session

    app.dependency_overrides[auth_api.get_db] = _db
    yield
    app.dependency_overrides.pop(auth_api.get_db, None)
    app.dependency_overrides.pop(auth_api.get_current_user, None)


def _raiser(exc):
    def _raise(*args):
        raise exc

    return _raise


# --- /password/forgot -------------------------------------------------------


def test_forgot_known_and_unknown_users_are_indistinguishable(monkeypatch):
    monkeypatch.setattr(auth_api, "forgot_password", lambda email: None)
    known = client.post("/api/auth/password/forgot", json={"email": "doctor@heimdall.test"})
    monkeypatch.setattr(
        auth_api, "forgot_password", _raiser(InvalidCredentialsError("UserNotFoundException"))
    )
    unknown = client.post("/api/auth/password/forgot", json={"email": "nobody@heimdall.test"})
    assert (
        (known.status_code, known.content) == (unknown.status_code, unknown.content) == (202, b"")
    )


def test_forgot_consumes_an_attempt_and_audits_without_email(monkeypatch):
    monkeypatch.setattr(auth_api, "forgot_password", lambda email: None)
    client.post("/api/auth/password/forgot", json={"email": "doctor@heimdall.test"})
    auth_api.register_login_failure.assert_called_once()
    kwargs = auth_api.log_audit.await_args.kwargs
    assert kwargs["action"] == "password_reset_requested"
    assert kwargs.get("metadata") is None


def test_forgot_cognito_rate_limit_is_still_202(monkeypatch):
    # Cognito's per-user limit would otherwise confirm the account exists.
    monkeypatch.setattr(auth_api, "forgot_password", _raiser(RateLimitedError("LimitExceeded")))
    resp = client.post("/api/auth/password/forgot", json={"email": "doctor@heimdall.test"})
    assert resp.status_code == 202


def test_forgot_outage_is_502(monkeypatch):
    monkeypatch.setattr(auth_api, "forgot_password", _raiser(CognitoError("InternalError")))
    resp = client.post("/api/auth/password/forgot", json={"email": "doctor@heimdall.test"})
    assert resp.status_code == 502


# --- /password/reset --------------------------------------------------------

RESET = {"email": "doctor@heimdall.test", "code": "123456", "new_password": NEW_PW}


def test_reset_success_is_204_audited_and_revokes_all_sessions(monkeypatch):
    monkeypatch.setattr(auth_api, "confirm_forgot_password", lambda e, c, p: None)
    resp = client.post("/api/auth/password/reset", json=RESET)
    assert resp.status_code == 204
    assert auth_api.log_audit.await_args.kwargs["action"] == "password_reset"
    found = _stub_side_effects.session.found_user
    assert found.sessions_revoked_at is not None
    assert found.session_keep_jti is None  # nothing survives a reset


def test_reset_bad_code_is_401_and_counted(monkeypatch):
    monkeypatch.setattr(
        auth_api, "confirm_forgot_password", _raiser(InvalidCredentialsError("CodeMismatch"))
    )
    resp = client.post("/api/auth/password/reset", json=RESET)
    assert resp.status_code == 401
    auth_api.register_login_failure.assert_called_once()
    assert NEW_PW not in resp.text


def test_reset_policy_violation_is_400(monkeypatch):
    monkeypatch.setattr(
        auth_api, "confirm_forgot_password", _raiser(PasswordPolicyError("not long enough"))
    )
    resp = client.post("/api/auth/password/reset", json=RESET)
    assert resp.status_code == 400 and "not long enough" in resp.json()["detail"]
    assert NEW_PW not in resp.text


def test_reset_rate_limited_is_429(monkeypatch):
    monkeypatch.setattr(
        auth_api, "confirm_forgot_password", _raiser(RateLimitedError("LimitExceeded"))
    )
    assert client.post("/api/auth/password/reset", json=RESET).status_code == 429


# --- /password/change -------------------------------------------------------

CHANGE = {"current_password": "Old-Horse-1!", "new_password": NEW_PW}


def _signed_in():
    user = MagicMock()
    user.id = uuid4()
    user.practice_id = uuid4()
    app.dependency_overrides[auth_api.get_current_user] = lambda: user
    return user


def test_change_requires_auth():
    resp = client.post("/api/auth/password/change", json=CHANGE)
    assert resp.status_code == 401


def test_change_uses_callers_own_token_and_audits_user(monkeypatch):
    user = _signed_in()
    calls = []
    monkeypatch.setattr(auth_api, "change_password", lambda tok, old, new: calls.append(tok))
    resp = client.post(
        "/api/auth/password/change", json=CHANGE, headers={"Authorization": "Bearer bearer-token"}
    )
    assert resp.status_code == 204
    assert calls == ["bearer-token"]  # Cognito scopes the change to this token's owner
    kwargs = auth_api.log_audit.await_args.kwargs
    assert kwargs["action"] == "password_change"
    assert kwargs["user_id"] == user.id and kwargs["practice_id"] == user.practice_id
    # Every other session is revoked; the one making the change is kept by jti.
    assert user.sessions_revoked_at is not None
    assert user.session_keep_jti == "this-jti"


def test_change_wrong_current_password_is_401_and_counted(monkeypatch):
    _signed_in()
    monkeypatch.setattr(
        auth_api, "change_password", _raiser(InvalidCredentialsError("NotAuthorized"))
    )
    resp = client.post(
        "/api/auth/password/change", json=CHANGE, headers={"Authorization": "Bearer t"}
    )
    assert resp.status_code == 401
    auth_api.register_login_failure.assert_called_once()
    assert CHANGE["current_password"] not in resp.text and NEW_PW not in resp.text


def test_change_policy_violation_is_400(monkeypatch):
    _signed_in()
    monkeypatch.setattr(auth_api, "change_password", _raiser(PasswordPolicyError("needs symbol")))
    resp = client.post(
        "/api/auth/password/change", json=CHANGE, headers={"Authorization": "Bearer t"}
    )
    assert resp.status_code == 400 and "needs symbol" in resp.json()["detail"]
