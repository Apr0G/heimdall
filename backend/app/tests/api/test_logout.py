"""POST /api/auth/logout must end the session server-side, not just clear the
cookie (MED-03 / LOW-17): access tokens are verified locally, so the revocation
stamp is the only thing that stops a captured token outliving sign-out."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.services.cognito import CognitoError

client = TestClient(app)


@pytest.fixture
def user():
    u = MagicMock()
    u.id = uuid4()
    u.practice_id = uuid4()
    u.sessions_revoked_at = None
    u.session_keep_jti = "keep"
    app.dependency_overrides[get_current_user] = lambda: u

    class _Session:
        async def commit(self):
            self.committed = True

    async def _db():
        yield _Session()

    app.dependency_overrides[get_db] = _db
    yield u
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    monkeypatch.setattr(auth_api, "log_audit", AsyncMock())
    monkeypatch.setattr(auth_api, "global_sign_out", MagicMock())


def test_logout_revokes_all_sessions_clears_cookie_and_audits(user):
    resp = client.post("/api/auth/logout", headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    assert user.sessions_revoked_at is not None and user.session_keep_jti is None
    auth_api.global_sign_out.assert_called_once_with("tok")
    assert "hd_session=" in resp.headers.get("set-cookie", "") and "Max-Age=0" in resp.headers.get(
        "set-cookie", ""
    )
    assert auth_api.log_audit.await_args.kwargs["action"] == "logout"


def test_logout_survives_cognito_outage_but_still_revokes(user):
    auth_api.global_sign_out.side_effect = CognitoError("InternalError")
    resp = client.post("/api/auth/logout", headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    assert user.sessions_revoked_at is not None
