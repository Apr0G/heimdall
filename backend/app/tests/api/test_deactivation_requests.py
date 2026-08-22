"""Deactivation requests: a user asks, an admin decides.

User side (auth router): one open request at a time, cancel withdraws it,
admins are emailed best-effort (a mail failure never fails the request).
Admin side: approve runs the real deactivation and resolves the request; deny
resolves it without touching the account; both audited; self-approval blocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import admin_users
from app.api import auth as auth_api
from app.api.admin import require_admin
from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.services.mailer import MailError

client = TestClient(app)


def _user(role="doctor", active=True):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.practice_id = uuid.uuid4()
    u.email = f"{u.id}@heimdall.test"
    u.full_name = "Dr. Jane Doe"
    u.role = role
    u.is_active = active
    u.last_login_at = datetime(2026, 8, 10, tzinfo=UTC)
    u.created_at = datetime(2026, 8, 1, tzinfo=UTC)
    u.sessions_revoked_at = None
    u.session_keep_jti = "k"
    u.deactivated_at = None
    return u


def _request(user, status="pending"):
    r = MagicMock()
    r.id = uuid.uuid4()
    r.user_id = user.id
    r.practice_id = user.practice_id
    r.reason = "Leaving the practice"
    r.status = status
    r.created_at = datetime(2026, 8, 20, tzinfo=UTC)
    r.resolved_by = None
    r.resolved_at = None
    return r


class UserSession:
    """Fake for the auth-router endpoints. Models the atomic insert: `scalar`
    on an INSERT returns the new id unless a pending row exists (the partial
    unique index), and on a SELECT returns the pending row."""

    def __init__(self, pending=None, admin_emails=()):
        self.pending = pending
        self.admin_emails = list(admin_emails)
        self.added = []
        self.committed = False

    async def scalar(self, stmt):
        if getattr(stmt, "is_insert", False) or type(stmt).__name__ == "Insert":
            if self.pending is not None:
                return None  # ON CONFLICT DO NOTHING → no row returned
            req = MagicMock()
            req.id = uuid.uuid4()
            req.status = "pending"
            req.created_at = datetime(2026, 8, 21, tzinfo=UTC)
            params = stmt.compile().params
            req.user_id = params.get("user_id")
            req.practice_id = params.get("practice_id")
            req.reason = params.get("reason")
            self.added.append(req)
            return req.id
        return self.pending

    async def get(self, model, pk):
        return next((r for r in self.added if r.id == pk), None)

    async def execute(self, stmt):
        res = MagicMock()
        res.scalars.return_value.all.return_value = self.admin_emails
        return res

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True


class AdminSession:
    """Fake for the admin-router endpoints."""

    def __init__(self, row=None):
        self.row = row  # (request, user, practice_name)
        self.committed = False

    async def execute(self, stmt):
        res = MagicMock()
        res.first.return_value = self.row
        res.all.return_value = [self.row] if self.row else []
        return res

    async def scalar(self, stmt):
        return self.row[0] if self.row and self.row[0].status == "pending" else None

    async def commit(self):
        self.committed = True


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    monkeypatch.setattr(auth_api, "log_audit", AsyncMock())
    monkeypatch.setattr(auth_api, "send_email", MagicMock())
    monkeypatch.setattr(admin_users, "log_audit", AsyncMock())
    monkeypatch.setattr(admin_users, "admin_set_enabled", MagicMock())
    yield
    for dep in (get_db, get_current_user, require_admin):
        app.dependency_overrides.pop(dep, None)


def _as(user, session):
    app.dependency_overrides[get_current_user] = lambda: user

    async def _dep():
        yield session

    app.dependency_overrides[get_db] = _dep
    return session


def _as_admin(admin, session):
    app.dependency_overrides[require_admin] = lambda: admin

    async def _dep():
        yield session

    app.dependency_overrides[get_db] = _dep
    return session


# --- user side -----------------------------------------------------------------


def test_request_creates_audits_and_emails_admins():
    me = _user()
    session = _as(me, UserSession(admin_emails=["admin@heimdall.test"]))
    resp = client.post("/api/auth/deactivation-request", json={"reason": "  Leaving <b>now</b>  "})
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"
    req = session.added[0]
    assert req.user_id == me.id and req.practice_id == me.practice_id
    assert req.reason == "Leaving <b>now</b>"
    assert session.committed
    assert auth_api.log_audit.await_args.kwargs["action"] == "deactivation_requested"
    kwargs = auth_api.send_email.call_args.kwargs
    assert kwargs["to"] == "admin@heimdall.test"
    assert "Leaving &lt;b&gt;now&lt;/b&gt;" in kwargs["html"]  # user text is escaped
    assert "Dr. Jane Doe" in kwargs["text"]


def test_request_mail_failure_does_not_fail_request():
    me = _user()
    auth_api.send_email.side_effect = MailError("MessageRejected")
    session = _as(me, UserSession(admin_emails=["admin@heimdall.test"]))
    assert client.post("/api/auth/deactivation-request", json={}).status_code == 201
    assert session.committed


def test_only_one_open_request():
    me = _user()
    _as(me, UserSession(pending=_request(me)))
    resp = client.post("/api/auth/deactivation-request", json={})
    assert resp.status_code == 409
    auth_api.send_email.assert_not_called()


def test_view_and_cancel_own_request():
    me = _user()
    pending = _request(me)
    session = _as(me, UserSession(pending=pending))
    assert client.get("/api/auth/deactivation-request").json()["status"] == "pending"
    resp = client.delete("/api/auth/deactivation-request")
    assert resp.status_code == 204
    assert pending.status == "denied" and pending.resolved_by == me.id
    assert auth_api.log_audit.await_args.kwargs["action"] == "deactivation_request_cancelled"
    assert session.committed


def test_cancel_without_request_is_404():
    _as(_user(), UserSession(pending=None))
    assert client.delete("/api/auth/deactivation-request").status_code == 404


def test_requires_auth():
    assert client.post("/api/auth/deactivation-request", json={}).status_code == 401


# --- admin side ----------------------------------------------------------------


def test_non_admin_cannot_list_or_resolve():
    app.dependency_overrides[get_current_user] = lambda: _user()
    assert client.get("/api/admin/deactivation-requests").status_code == 403
    assert client.post(f"/api/admin/deactivation-requests/{uuid.uuid4()}/deny").status_code == 403


def test_list_pending_requests():
    admin = _user(role="admin")
    target = _user()
    req = _request(target)
    _as_admin(admin, AdminSession(row=(req, target, "Sunrise")))
    body = client.get("/api/admin/deactivation-requests").json()
    assert len(body) == 1
    assert body[0]["reason"] == "Leaving the practice"
    assert (
        body[0]["user"]["email"] == target.email and body[0]["user"]["practice_name"] == "Sunrise"
    )


def test_approve_runs_deactivation_and_resolves():
    admin = _user(role="admin")
    target = _user()
    req = _request(target)
    session = _as_admin(admin, AdminSession(row=(req, target, "Sunrise")))
    resp = client.post(f"/api/admin/deactivation-requests/{req.id}/approve")
    assert resp.status_code == 200, resp.text
    admin_users.admin_set_enabled.assert_called_once_with(target.email, False)
    assert target.is_active is False and target.sessions_revoked_at is not None
    assert req.status == "approved" and req.resolved_by == admin.id
    assert admin_users.log_audit.await_args.kwargs["action"] == "user_deactivated"
    assert session.committed
    assert resp.json()["is_active"] is False


def test_deny_resolves_without_touching_account():
    admin = _user(role="admin")
    target = _user()
    req = _request(target)
    session = _as_admin(admin, AdminSession(row=(req, target, "Sunrise")))
    resp = client.post(f"/api/admin/deactivation-requests/{req.id}/deny")
    assert resp.status_code == 200
    admin_users.admin_set_enabled.assert_not_called()
    assert target.is_active is True
    assert req.status == "denied" and req.resolved_by == admin.id
    assert admin_users.log_audit.await_args.kwargs["action"] == "deactivation_request_denied"
    assert session.committed


def test_resolved_request_cannot_be_resolved_again():
    admin = _user(role="admin")
    target = _user()
    req = _request(target, status="denied")
    _as_admin(admin, AdminSession(row=(req, target, "Sunrise")))
    assert client.post(f"/api/admin/deactivation-requests/{req.id}/approve").status_code == 409


def test_admin_cannot_approve_own_request():
    admin = _user(role="admin")
    req = _request(admin)
    _as_admin(admin, AdminSession(row=(req, admin, "Heimdall Internal")))
    assert client.post(f"/api/admin/deactivation-requests/{req.id}/approve").status_code == 400
    admin_users.admin_set_enabled.assert_not_called()
