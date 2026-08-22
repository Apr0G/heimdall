"""Lost-authenticator recovery: password + emailed code -> identity recreated.

Pins the gate order (password first, nothing emailed or changed otherwise), the
attempt accounting, that the users row is rebound to the new sub with every
session revoked, and the audit actions.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.main import app
from app.services.cognito import CognitoError, InvalidCredentialsError
from app.services.mailer import MailError

client = TestClient(app)
START = {"email": "Doctor@Heimdall.test ", "password": "Correct-Horse-9!"}
COMPLETE = {**START, "code": "654321"}


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    monkeypatch.setattr(auth_api, "login_allowed", lambda key: True)
    monkeypatch.setattr(auth_api, "register_login_failure", MagicMock())
    monkeypatch.setattr(auth_api, "log_audit", AsyncMock())
    monkeypatch.setattr(
        auth_api, "password_challenge", MagicMock(return_value="SOFTWARE_TOKEN_MFA")
    )
    monkeypatch.setattr(auth_api, "send_email", MagicMock())
    monkeypatch.setattr(auth_api, "issue_code", MagicMock(return_value="654321"))
    monkeypatch.setattr(auth_api, "verify_code", MagicMock(return_value=True))
    monkeypatch.setattr(auth_api, "admin_recreate_user", MagicMock(return_value="new-sub"))

    class _Session:
        found_user = MagicMock(
            cognito_sub="old-sub", sessions_revoked_at=None, session_keep_jti="k"
        )

        async def scalar(self, stmt):
            return self.found_user

        async def commit(self):
            self.committed = True

    _stubs.session = _Session()

    async def _db():
        yield _stubs.session

    app.dependency_overrides[auth_api.get_db] = _db
    yield
    app.dependency_overrides.pop(auth_api.get_db, None)


# --- start --------------------------------------------------------------------


def test_start_emails_a_code_after_password_check():
    resp = client.post("/api/auth/mfa/recover/start", json=START)
    assert resp.status_code == 202
    auth_api.password_challenge.assert_called_once_with("doctor@heimdall.test", "Correct-Horse-9!")
    auth_api.issue_code.assert_called_once_with("doctor@heimdall.test")
    kwargs = auth_api.send_email.call_args.kwargs
    assert kwargs["to"] == "doctor@heimdall.test" and "654321" in kwargs["text"]
    assert "654321" not in resp.text
    auth_api.register_login_failure.assert_called_once()  # each send costs an attempt
    assert auth_api.log_audit.await_args.kwargs["action"] == "mfa_reset_requested"


def test_start_wrong_password_sends_nothing():
    auth_api.password_challenge.side_effect = InvalidCredentialsError("NotAuthorized")
    resp = client.post("/api/auth/mfa/recover/start", json=START)
    assert resp.status_code == 401
    auth_api.issue_code.assert_not_called()
    auth_api.send_email.assert_not_called()


def test_start_without_enrolled_authenticator_is_400():
    auth_api.password_challenge.return_value = "MFA_SETUP"
    resp = client.post("/api/auth/mfa/recover/start", json=START)
    assert resp.status_code == 400 and "no authenticator" in resp.json()["detail"]
    auth_api.send_email.assert_not_called()


def test_start_mail_failure_is_502():
    auth_api.send_email.side_effect = MailError("MessageRejected")
    assert client.post("/api/auth/mfa/recover/start", json=START).status_code == 502


# --- complete -----------------------------------------------------------------


def test_complete_recreates_identity_rebinds_and_revokes():
    resp = client.post("/api/auth/mfa/recover/complete", json=COMPLETE)
    assert resp.status_code == 204, resp.text
    auth_api.verify_code.assert_called_once_with("doctor@heimdall.test", "654321")
    auth_api.admin_recreate_user.assert_called_once_with("doctor@heimdall.test", "Correct-Horse-9!")
    user = _stubs.session.found_user
    assert user.cognito_sub == "new-sub"
    assert user.sessions_revoked_at is not None and user.session_keep_jti is None
    assert auth_api.log_audit.await_args.kwargs["action"] == "mfa_reset"


def test_complete_wrong_code_changes_nothing():
    auth_api.verify_code.return_value = False
    resp = client.post("/api/auth/mfa/recover/complete", json=COMPLETE)
    assert resp.status_code == 401
    auth_api.admin_recreate_user.assert_not_called()
    auth_api.register_login_failure.assert_called_once()
    assert _stubs.session.found_user.cognito_sub == "old-sub"


def test_complete_checks_password_before_code():
    auth_api.password_challenge.side_effect = InvalidCredentialsError("NotAuthorized")
    resp = client.post("/api/auth/mfa/recover/complete", json=COMPLETE)
    assert resp.status_code == 401
    auth_api.verify_code.assert_not_called()  # a wrong password must not burn the code
    auth_api.admin_recreate_user.assert_not_called()


def test_complete_unprovisioned_user_is_refused_before_cognito_changes():
    _stubs.session.found_user = None
    resp = client.post("/api/auth/mfa/recover/complete", json=COMPLETE)
    assert resp.status_code == 403
    auth_api.admin_recreate_user.assert_not_called()


def test_complete_cognito_failure_is_502_and_row_untouched():
    auth_api.admin_recreate_user.side_effect = CognitoError("InternalError")
    resp = client.post("/api/auth/mfa/recover/complete", json=COMPLETE)
    assert resp.status_code == 502
    assert _stubs.session.found_user.cognito_sub == "old-sub"


def test_complete_marks_row_reset_pending_when_recreate_fails_after_delete():
    # Old identity gone, new one couldn't be finished: the row must be flagged
    # so an admin re-invite can rebind it, and the user told what to do.
    from app.services.cognito import IdentityResetIncomplete
    from app.services.provisioning import RESET_PENDING_PREFIX

    auth_api.admin_recreate_user.side_effect = IdentityResetIncomplete("ClientError")
    resp = client.post("/api/auth/mfa/recover/complete", json=COMPLETE)
    assert resp.status_code == 502
    assert "new invitation" in resp.json()["detail"]
    user = _stubs.session.found_user
    assert user.cognito_sub.startswith(RESET_PENDING_PREFIX)
    assert user.sessions_revoked_at is not None
    assert auth_api.log_audit.await_args.kwargs["action"] == "mfa_reset_failed"
