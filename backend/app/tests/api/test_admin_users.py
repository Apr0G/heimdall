"""HTTP contract of the admin user-management routes. Cognito and the DB are
stubbed; these pin the role gate, the self-deactivation guard, Cognito-before-DB
ordering, session revocation on deactivate, and the audit actions."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import admin_users
from app.api.admin import require_admin
from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.services.cognito import CognitoError, InvalidCredentialsError

client = TestClient(app)


def _user(role="doctor", last_login=None, active=True):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.practice_id = uuid.uuid4()
    u.email = f"{u.id}@heimdall.test"
    u.full_name = None
    u.role = role
    u.is_active = active
    u.last_login_at = last_login
    u.created_at = datetime(2026, 8, 1, tzinfo=UTC)
    u.sessions_revoked_at = None
    u.session_keep_jti = "keep"
    u.deactivated_at = None
    return u


class FakeSession:
    def __init__(self, target=None, pending=None):
        self.target = target
        self.pending = pending  # an open DeactivationRequest for the target, if any
        self.practice = MagicMock(name="practice")
        self.practice.name = "Sunrise"
        self.committed = False

    async def scalar(self, stmt):
        return self.pending

    async def execute(self, stmt):
        res = MagicMock()
        res.first.return_value = None if self.target is None else (self.target, self.practice)
        return res

    async def commit(self):
        self.committed = True


@pytest.fixture
def admin():
    a = _user(role="admin")
    app.dependency_overrides[require_admin] = lambda: a
    yield a
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    monkeypatch.setattr(admin_users, "log_audit", AsyncMock())
    monkeypatch.setattr(admin_users, "admin_set_enabled", MagicMock())
    monkeypatch.setattr(admin_users, "admin_invite", MagicMock(return_value=("sub", False)))
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _db(session):
    async def _dep():
        yield session

    app.dependency_overrides[get_db] = _dep
    return session


def test_non_admin_gets_403():
    doctor = _user()
    app.dependency_overrides[get_current_user] = lambda: doctor
    assert client.get("/api/admin/users").status_code == 403
    assert client.post(f"/api/admin/users/{uuid.uuid4()}/deactivate").status_code == 403


def test_cannot_deactivate_self(admin):
    _db(FakeSession(target=admin))
    resp = client.post(f"/api/admin/users/{admin.id}/deactivate")
    assert resp.status_code == 400
    admin_users.admin_set_enabled.assert_not_called()


def test_deactivate_disables_cognito_first_then_revokes_and_audits(admin):
    target = _user(last_login=datetime(2026, 8, 10, tzinfo=UTC))
    session = _db(FakeSession(target=target))
    resp = client.post(f"/api/admin/users/{target.id}/deactivate")
    assert resp.status_code == 200, resp.text
    admin_users.admin_set_enabled.assert_called_once_with(target.email, False)
    assert target.is_active is False
    assert target.sessions_revoked_at is not None and target.session_keep_jti is None
    assert session.committed
    kwargs = admin_users.log_audit.await_args.kwargs
    assert kwargs["action"] == "user_deactivated"
    assert kwargs["user_id"] == admin.id and kwargs["resource_id"] == target.id
    assert resp.json()["is_active"] is False


def test_deactivate_cognito_failure_leaves_db_untouched(admin):
    target = _user()
    session = _db(FakeSession(target=target))
    admin_users.admin_set_enabled.side_effect = CognitoError("InternalError")
    resp = client.post(f"/api/admin/users/{target.id}/deactivate")
    assert resp.status_code == 502
    assert target.is_active is True and not session.committed
    admin_users.log_audit.assert_not_awaited()


def test_reactivate_keeps_old_sessions_dead(admin):
    target = _user(active=False)
    target.sessions_revoked_at = datetime(2026, 8, 20, tzinfo=UTC)
    _db(FakeSession(target=target))
    resp = client.post(f"/api/admin/users/{target.id}/reactivate")
    assert resp.status_code == 200
    admin_users.admin_set_enabled.assert_called_once_with(target.email, True)
    assert target.is_active is True
    assert target.sessions_revoked_at is not None  # they must log in fresh
    assert admin_users.log_audit.await_args.kwargs["action"] == "user_reactivated"


def test_unknown_user_is_404(admin):
    _db(FakeSession(target=None))
    assert client.post(f"/api/admin/users/{uuid.uuid4()}/deactivate").status_code == 404


def test_resend_invite_only_while_pending(admin):
    signed_in = _user(last_login=datetime(2026, 8, 10, tzinfo=UTC))
    _db(FakeSession(target=signed_in))
    assert client.post(f"/api/admin/users/{signed_in.id}/resend-invite").status_code == 409
    admin_users.admin_invite.assert_not_called()

    pending = _user(last_login=None)
    _db(FakeSession(target=pending))
    resp = client.post(f"/api/admin/users/{pending.id}/resend-invite")
    assert resp.status_code == 200
    admin_users.admin_invite.assert_called_once_with(pending.email)
    assert resp.json()["invite_pending"] is True
    assert admin_users.log_audit.await_args.kwargs["action"] == "user_invite_resent"


def test_resend_when_cognito_says_already_activated_is_409(admin):
    pending = _user(last_login=None)
    _db(FakeSession(target=pending))
    admin_users.admin_invite.side_effect = InvalidCredentialsError("NotAuthorizedException")
    assert client.post(f"/api/admin/users/{pending.id}/resend-invite").status_code == 409


def test_invite_validation_error_is_400(admin, monkeypatch):
    _db(FakeSession())

    async def _raise(*a, **k):
        raise admin_users.ProvisioningError("Choose an existing practice or name a new one")

    monkeypatch.setattr(admin_users, "invite_user", _raise)
    resp = client.post("/api/admin/users", json={"email": "a@b.com", "role": "doctor"})
    assert resp.status_code == 400 and "existing practice" in resp.json()["detail"]
    admin_users.log_audit.assert_not_awaited()


def test_invite_success_audits_and_returns_item(admin, monkeypatch):
    session = _db(FakeSession())
    new_user = _user()
    practice = MagicMock()
    practice.name = "Sunrise"
    result = MagicMock(
        user=new_user,
        practice=practice,
        created_user=True,
        created_practice=True,
        created_cognito=True,
    )

    async def _ok(*a, **k):
        return result

    monkeypatch.setattr(admin_users, "invite_user", _ok)
    resp = client.post(
        "/api/admin/users",
        json={"email": new_user.email, "role": "doctor", "practice_name": "Sunrise"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created_user"] and body["created_practice"] and not body["invite_resent"]
    assert body["user"]["practice_name"] == "Sunrise" and body["user"]["invite_pending"] is True
    assert session.committed
    assert admin_users.log_audit.await_args.kwargs["action"] == "user_invited"


def test_manual_deactivate_marks_open_request_approved(admin):
    target = _user()
    pending = MagicMock(status="pending", resolved_by=None, resolved_at=None)
    session = _db(FakeSession(target=target, pending=pending))
    resp = client.post(f"/api/admin/users/{target.id}/deactivate")
    assert resp.status_code == 200
    assert pending.status == "approved" and pending.resolved_by == admin.id
    assert session.committed
