import logging

import boto3
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.rate_limit import ip_key, limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/leads", tags=["leads"])

_sns = None


def _sns_client():
    global _sns
    if _sns is None:
        _sns = boto3.client("sns", region_name=settings.aws_region)
    return _sns


class LeadRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    practice: str = Field(min_length=1, max_length=2000)


# Public endpoint: IP-keyed so a forged JWT sub can't mint a fresh bucket per request.
@router.post("", status_code=202)
@limiter.limit(settings.rate_limit_public, key_func=ip_key)
async def submit_lead(request: Request, response: Response, lead: LeadRequest) -> dict[str, str]:
    """Public 'get started' intake. Publishes the lead to SNS (email to the
    founder). No PHI here — this is prospect contact info, not patient data."""
    if not settings.leads_topic_arn:
        raise HTTPException(status_code=503, detail="Lead intake is not configured yet.")

    body = (
        "New Heimdall lead\n\n"
        f"Name: {lead.name}\n"
        f"Email: {lead.email}\n\n"
        f"Practice:\n{lead.practice}\n"
    )
    await run_in_threadpool(
        lambda: _sns_client().publish(
            TopicArn=settings.leads_topic_arn,
            Subject="New Heimdall lead",
            Message=body,
        )
    )
    # Log only the email domain — never the full contact details.
    logger.info(
        "lead submitted", extra={"context": {"email_domain": lead.email.rsplit("@", 1)[-1]}}
    )
    return {"status": "received"}
