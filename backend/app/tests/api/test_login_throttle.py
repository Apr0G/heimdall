"""The fail-closed login throttle on the real routes (MED-30). Every other auth
test stubs login_allowed open; these prove a closed throttle yields 429 before
any Cognito call, on each throttled endpoint, and that a storage error closes
it rather than opening it."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.core import rate_limit
from app.main import app

client = TestClient(app)

THROTTLED = [
    ("/api/auth/login", {"email": "a@b.com", "password": "x"}),
    ("/api/auth/password/set", {"email": "a@b.com", "session": "s", "new_password": "x"}),
    ("/api/auth/password/forgot", {"email": "a@b.com"}),
    ("/api/auth/password/reset", {"email": "a@b.com", "code": "1", "new_password": "x"}),
    ("/api/auth/mfa/recover/start", {"email": "a@b.com", "password": "x"}),
    # The identity-recreation surface, the highest-risk unauthenticated one — accepts
    # a password plus an emailed one-time code and rebinds the Cognito identity.
    ("/api/auth/mfa/recover/complete", {"email": "a@b.com", "password": "x", "code": "1"}),
    ("/api/auth/mfa/verify", {"email": "a@b.com", "session": "s", "code": "1"}),
    # MFA-setup endpoints accept TOTP guesses; both must throttle too.
    ("/api/auth/mfa/setup/start", {"email": "a@b.com", "session": "s"}),
    ("/api/auth/mfa/setup/complete", {"email": "a@b.com", "session": "s", "code": "1"}),
]


@pytest.mark.parametrize("path,body", THROTTLED)
def test_closed_throttle_is_429_before_cognito(monkeypatch, path, body):
    monkeypatch.setattr(auth_api, "login_allowed", lambda key: False)
    cognito = MagicMock()
    for name in (
        "initiate_auth",
        "respond_new_password",
        "forgot_password",
        "confirm_forgot_password",
        "password_challenge",
        "respond_software_token_mfa",
        "recover_password",
        "verify_code",
        "start_mfa_setup",
        "complete_mfa_setup",
        "admin_recreate_user",
    ):
        if hasattr(auth_api, name):
            monkeypatch.setattr(auth_api, name, cognito)
    resp = client.post(path, json=body)
    assert resp.status_code == 429
    cognito.assert_not_called()


def test_storage_error_fails_closed(monkeypatch):
    class Broken:
        def test(self, *a, **k):
            raise ConnectionError("redis down")

    monkeypatch.setattr(rate_limit, "_login_strategy", Broken())
    assert rate_limit.login_allowed("ip:anyone") is False
