"""Mailer provider switch: dispatch, the SMTP2GO payload/response contract, and
the never-log-recipient rule (provider error bodies echo the address)."""

import json

import pytest

from app.core.config import settings
from app.services import mailer


class _Response:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


@pytest.fixture
def smtp2go(monkeypatch):
    """Route sends through smtp2go with a test key; capture the HTTP call."""
    monkeypatch.setattr(settings, "mail_provider", "smtp2go")
    monkeypatch.setattr(settings, "smtp2go_api_key", "test-key-not-real")
    calls: list[dict] = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers})
        return _Response(200, {"data": {"succeeded": 1, "failed": 0}})

    monkeypatch.setattr(mailer.httpx, "post", fake_post)
    return calls


def _send():
    mailer.send_email(
        to="user@example.test", subject="Your code", text="123456", html="<b>123456</b>"
    )


class TestDispatch:
    def test_default_is_ses(self, monkeypatch):
        monkeypatch.setattr(settings, "mail_provider", "ses")
        seen = {}
        monkeypatch.setattr(mailer, "_send_ses", lambda **kw: seen.update(kw))
        _send()
        assert seen["to"] == "user@example.test"

    def test_smtp2go_selected(self, smtp2go):
        _send()
        assert len(smtp2go) == 1


class TestSmtp2go:
    def test_payload_contract(self, smtp2go):
        _send()
        call = smtp2go[0]
        assert call["url"] == "https://api.smtp2go.com/v3/email/send"
        assert call["headers"]["X-Smtp2go-Api-Key"] == "test-key-not-real"
        body = call["json"]
        assert body["sender"] == settings.mail_from
        assert body["to"] == ["user@example.test"]
        assert body["text_body"] == "123456" and body["html_body"] == "<b>123456</b>"
        assert {"header": "Reply-To", "value": settings.mail_reply_to} in body["custom_headers"]

    def test_missing_key_fails_loud(self, monkeypatch):
        monkeypatch.setattr(settings, "mail_provider", "smtp2go")
        monkeypatch.setattr(settings, "smtp2go_api_key", "")
        with pytest.raises(mailer.MailError, match="MissingApiKey"):
            _send()

    @pytest.mark.parametrize(
        ("response", "code"),
        [
            (_Response(401, {"data": {}}), "HTTP401"),
            (_Response(200, {"data": {"succeeded": 0, "failed": 1}}), "SendRejected"),
            (_Response(200, None), "BadResponse"),
        ],
    )
    def test_failures_raise_mail_error(self, monkeypatch, response, code):
        monkeypatch.setattr(settings, "mail_provider", "smtp2go")
        monkeypatch.setattr(settings, "smtp2go_api_key", "test-key-not-real")
        monkeypatch.setattr(mailer.httpx, "post", lambda *a, **k: response)
        with pytest.raises(mailer.MailError, match=code):
            _send()

    def test_transport_error_raises_mail_error(self, monkeypatch):
        monkeypatch.setattr(settings, "mail_provider", "smtp2go")
        monkeypatch.setattr(settings, "smtp2go_api_key", "test-key-not-real")

        def boom(*a, **k):
            raise mailer.httpx.ConnectError("no route")

        monkeypatch.setattr(mailer.httpx, "post", boom)
        with pytest.raises(mailer.MailError, match="ConnectError"):
            _send()

    def test_failure_logs_never_carry_recipient_or_code(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "mail_provider", "smtp2go")
        monkeypatch.setattr(settings, "smtp2go_api_key", "test-key-not-real")
        monkeypatch.setattr(
            mailer.httpx,
            "post",
            lambda *a, **k: _Response(400, {"data": {"error": "bad address user@example.test"}}),
        )
        with caplog.at_level("WARNING"), pytest.raises(mailer.MailError):
            _send()
        logged = " ".join(
            json.dumps(getattr(r, "context", "")) + r.getMessage() for r in caplog.records
        )
        assert "user@example.test" not in logged
        assert "123456" not in logged
