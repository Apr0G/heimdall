"""Outbound transactional email — provider-switched via settings.mail_provider.

Used only for messages the API must send itself — today just
authenticator-recovery codes. Providers: "ses" (sesv2, the default) and
"smtp2go" (HTTPS API; added while the SES account is stuck in the sandbox,
which refuses mail to unverified recipients).

Two invariants, regardless of provider:
* These emails carry one-time auth codes addressed to practice staff — NEVER
  PHI. That rule is what makes a non-BAA provider acceptable here; anything
  patient-related must not go through this module.
* Never log bodies, subjects, or recipients — they contain one-time codes
  addressed to a specific person (and provider error bodies echo the address).
  Log provider + error code only.
"""

import logging

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

_SMTP2GO_ENDPOINT = "https://api.smtp2go.com/v3/email/send"


class MailError(Exception):
    """The provider refused or failed the send."""


_client = None


def _get_ses_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "sesv2",
            region_name=settings.aws_region,
            config=Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2}),
        )
    return _client


def _fail(provider: str, code: str) -> None:
    logger.warning("mail send failed", extra={"context": {"provider": provider, "code": code}})
    raise MailError(code)


def _send_ses(*, to: str, subject: str, text: str, html: str) -> None:
    try:
        _get_ses_client().send_email(
            FromEmailAddress=settings.mail_from,
            ReplyToAddresses=[settings.mail_reply_to] if settings.mail_reply_to else [],
            Destination={"ToAddresses": [to]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text, "Charset": "UTF-8"},
                        "Html": {"Data": html, "Charset": "UTF-8"},
                    },
                }
            },
        )
    except (ClientError, BotoCoreError) as exc:
        code = exc.response.get("Error", {}).get("Code", "") if isinstance(exc, ClientError) else ""
        logger.warning(
            "mail send failed",
            extra={"context": {"provider": "ses", "code": code or type(exc).__name__}},
        )
        raise MailError(code or type(exc).__name__) from exc


def _send_smtp2go(*, to: str, subject: str, text: str, html: str) -> None:
    if not settings.smtp2go_api_key:
        _fail("smtp2go", "MissingApiKey")
    payload = {
        "sender": settings.mail_from,
        "to": [to],
        "subject": subject,
        "text_body": text,
        "html_body": html,
    }
    if settings.mail_reply_to:
        payload["custom_headers"] = [{"header": "Reply-To", "value": settings.mail_reply_to}]
    try:
        response = httpx.post(
            _SMTP2GO_ENDPOINT,
            json=payload,
            headers={"X-Smtp2go-Api-Key": settings.smtp2go_api_key},
            timeout=httpx.Timeout(15, connect=5),
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "mail send failed",
            extra={"context": {"provider": "smtp2go", "code": type(exc).__name__}},
        )
        raise MailError(type(exc).__name__) from exc
    if response.status_code >= 400:
        # Status code only — the response body echoes the recipient address.
        _fail("smtp2go", f"HTTP{response.status_code}")
    try:
        succeeded = response.json().get("data", {}).get("succeeded", 0)
    except ValueError:
        _fail("smtp2go", "BadResponse")
        return
    if succeeded != 1:
        # A 200 with a failures list still means nothing was delivered.
        _fail("smtp2go", "SendRejected")


def send_email(*, to: str, subject: str, text: str, html: str) -> None:
    """Synchronous (boto3/httpx); call via a threadpool."""
    if settings.mail_provider == "smtp2go":
        _send_smtp2go(to=to, subject=subject, text=text, html=html)
    else:
        _send_ses(to=to, subject=subject, text=text, html=html)
