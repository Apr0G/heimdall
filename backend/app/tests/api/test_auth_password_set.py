"""Route-level behaviour of POST /api/auth/password/set (NEW_PASSWORD_REQUIRED).

The Cognito service and the DB-backed helpers are stubbed: these tests pin the
HTTP contract (status codes, the challenge hand-off, that the password never
appears in any response) — not Cognito itself, which test_cognito_mfa covers.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.main import app
from app.schemas.auth import LoginResponse
from app.services.cognito import (
    AuthResult,
    CognitoError,
    InvalidCredentialsError,
    PasswordPolicyError,
)

client = TestClient(app)
BODY = {"email": "doctor@heimdall.test", "session": "sess-1", "new_password": "Correct-Horse-9!"}


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    # No Redis, no DB: the throttle always allows and the audit helpers are no-ops.
    monkeypatch.setattr(auth_api, "login_allowed", lambda key: True)
    monkeypatch.setattr(auth_api, "register_login_failure", lambda key: None)
    monkeypatch.setattr(auth_api, "log_audit", AsyncMock())
    monkeypatch.setattr(
        auth_api, "_finalize_login", AsyncMock(return_value=LoginResponse(expires_in=3600))
    )

    class _Session:
        async def commit(self):
            pass

    async def _db():
        yield _Session()

    app.dependency_overrides[auth_api.get_db] = _db
    yield
    app.dependency_overrides.pop(auth_api.get_db, None)


def test_chains_into_mfa_setup(monkeypatch):
    monkeypatch.setattr(
        auth_api,
        "respond_new_password",
        lambda e, s, p: AuthResult(challenge="MFA_SETUP", session="sess-2"),
    )
    resp = client.post("/api/auth/password/set", json=BODY)
    assert resp.status_code == 200
    assert resp.json()["mfa"] == {"challenge": "MFA_SETUP", "session": "sess-2"}
    assert BODY["new_password"] not in resp.text
    auth_api.log_audit.assert_awaited_once()
    assert auth_api.log_audit.await_args.kwargs["action"] == "password_set"


def test_tokens_finalize_login(monkeypatch):
    monkeypatch.setattr(
        auth_api, "respond_new_password", lambda e, s, p: AuthResult(tokens={"AccessToken": "t"})
    )
    client.post("/api/auth/password/set", json=BODY)
    auth_api._finalize_login.assert_awaited_once()
    assert auth_api._finalize_login.await_args.args[3] == {"AccessToken": "t"}


def test_policy_violation_is_400_with_reason(monkeypatch):
    def _raise(e, s, p):
        raise PasswordPolicyError("Password must have symbol characters")

    monkeypatch.setattr(auth_api, "respond_new_password", _raise)
    resp = client.post("/api/auth/password/set", json=BODY)
    assert resp.status_code == 400
    assert "symbol characters" in resp.json()["detail"]
    assert BODY["new_password"] not in resp.text
    auth_api.log_audit.assert_not_awaited()  # not a failed credential, not an outage


def test_stale_session_is_401(monkeypatch):
    def _raise(e, s, p):
        raise InvalidCredentialsError("NotAuthorizedException")

    monkeypatch.setattr(auth_api, "respond_new_password", _raise)
    resp = client.post("/api/auth/password/set", json=BODY)
    assert resp.status_code == 401
    assert auth_api.log_audit.await_args.kwargs["action"] == "login_failure"


def test_cognito_outage_is_502(monkeypatch):
    def _raise(e, s, p):
        raise CognitoError("InternalErrorException")

    monkeypatch.setattr(auth_api, "respond_new_password", _raise)
    resp = client.post("/api/auth/password/set", json=BODY)
    assert resp.status_code == 502
    assert auth_api.log_audit.await_args.kwargs["action"] == "login_error"
