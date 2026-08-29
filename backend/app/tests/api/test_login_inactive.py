"""A deactivated account must not get a session at login (LOW-03).

`_finalize_login` used to set the cookie and write `login_success` for an
`is_active=False` user; every request afterwards 401'd in get_current_user, so
the account was "logged in" for exactly zero requests while the audit trail said
otherwise. Cognito and the DB helpers are stubbed; this pins the HTTP contract.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.main import app
from app.services.cognito import AuthResult

BODY = {"email": "doctor@heimdall.test", "password": "Correct-Horse-9!"}


class _Session:
    def __init__(self):
        self.committed = 0
        self.rolled_back = 0

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


def _user(*, active: bool):
    u = MagicMock()
    u.id = uuid4()
    u.practice_id = uuid4()
    u.is_active = active
    return u


@pytest.fixture
def session():
    s = _Session()

    async def _db():
        yield s

    app.dependency_overrides[auth_api.get_db] = _db
    yield s
    app.dependency_overrides.pop(auth_api.get_db, None)


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    monkeypatch.setattr(auth_api, "login_allowed", lambda key: True)
    monkeypatch.setattr(auth_api, "register_login_failure", lambda key: None)
    monkeypatch.setattr(auth_api, "log_audit", AsyncMock())
    monkeypatch.setattr(
        auth_api,
        "initiate_auth",
        lambda e, p: AuthResult(tokens={"AccessToken": "tok", "ExpiresIn": 3600}),
    )
    monkeypatch.setattr(auth_api, "verify_access_token", AsyncMock(return_value={"sub": "sub-1"}))


def test_deactivated_user_is_refused_before_any_cookie(monkeypatch, session):
    monkeypatch.setattr(auth_api, "link_user_on_login", AsyncMock(return_value=_user(active=False)))
    resp = TestClient(app).post("/api/auth/login", json=BODY)
    assert resp.status_code == 401
    # Same wording as a wrong password: the response must not confirm that the
    # account exists but is disabled.
    assert resp.json()["detail"] == "Invalid email or password"
    assert "set-cookie" not in resp.headers
    # The last_login_at stamp link_user_on_login flushed is discarded — the
    # admin page must not show a login that never happened.
    assert session.rolled_back == 1 and session.committed == 1
    actions = [c.kwargs["action"] for c in auth_api.log_audit.await_args_list]
    assert actions == ["login_denied"]
    assert auth_api.log_audit.await_args.kwargs["metadata"] == {"reason": "deactivated"}


def test_active_user_gets_the_cookie(monkeypatch, session):
    """Positive control for the test above."""
    monkeypatch.setattr(auth_api, "link_user_on_login", AsyncMock(return_value=_user(active=True)))
    resp = TestClient(app).post("/api/auth/login", json=BODY)
    assert resp.status_code == 200
    assert "hd_session=" in resp.headers.get("set-cookie", "")
    assert session.rolled_back == 0
    assert auth_api.log_audit.await_args.kwargs["action"] == "login_success"
