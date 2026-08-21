"""Outbound transactional email via SES (sesv2). Used only for messages the API
must send itself — today just authenticator-recovery codes. Never log bodies:
they contain one-time codes addressed to a specific person."""

import logging

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class MailError(Exception):
    """SES refused or failed the send."""


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "sesv2",
            region_name=settings.aws_region,
            config=Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2}),
        )
    return _client


def send_email(*, to: str, subject: str, text: str, html: str) -> None:
    """Synchronous (boto3); call via a threadpool."""
    try:
        _get_client().send_email(
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
        logger.warning("ses send failed", extra={"context": {"code": code or type(exc).__name__}})
        raise MailError(code or type(exc).__name__) from exc
