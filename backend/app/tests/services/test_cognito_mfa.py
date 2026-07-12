from unittest.mock import MagicMock

import pytest

from app.services import cognito


def _mock_client(monkeypatch) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr(cognito, "_client", client)
    return client


def test_initiate_auth_returns_tokens(monkeypatch):
    client = _mock_client(monkeypatch)
    client.initiate_auth.return_value = {"AuthenticationResult": {"AccessToken": "tok"}}
    res = cognito.initiate_auth("a@b.com", "pw")
    assert res.tokens == {"AccessToken": "tok"}
    assert res.challenge is None and res.session is None


def test_initiate_auth_surfaces_mfa_challenge(monkeypatch):
    client = _mock_client(monkeypatch)
    client.initiate_auth.return_value = {"ChallengeName": "SOFTWARE_TOKEN_MFA", "Session": "s1"}
    res = cognito.initiate_auth("a@b.com", "pw")
    assert res.tokens is None
    assert res.challenge == "SOFTWARE_TOKEN_MFA"
    assert res.session == "s1"


def test_initiate_auth_setup_challenge(monkeypatch):
    client = _mock_client(monkeypatch)
    client.initiate_auth.return_value = {"ChallengeName": "MFA_SETUP", "Session": "s2"}
    res = cognito.initiate_auth("a@b.com", "pw")
    assert res.challenge == "MFA_SETUP" and res.session == "s2"


def test_initiate_auth_unsupported_challenge_raises(monkeypatch):
    client = _mock_client(monkeypatch)
    client.initiate_auth.return_value = {"ChallengeName": "NEW_PASSWORD_REQUIRED", "Session": "s"}
    with pytest.raises(cognito.CognitoError):
        cognito.initiate_auth("a@b.com", "pw")


def test_start_mfa_setup_returns_secret(monkeypatch):
    client = _mock_client(monkeypatch)
    client.associate_software_token.return_value = {"SecretCode": "BASE32SECRET", "Session": "s3"}
    out = cognito.start_mfa_setup("s2")
    assert out == {"secret": "BASE32SECRET", "session": "s3"}


def test_complete_mfa_setup_rejects_unverified(monkeypatch):
    client = _mock_client(monkeypatch)
    client.verify_software_token.return_value = {"Status": "ERROR"}
    with pytest.raises(cognito.InvalidCredentialsError):
        cognito.complete_mfa_setup("a@b.com", "s3", "000000")
