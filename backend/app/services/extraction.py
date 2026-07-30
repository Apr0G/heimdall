import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core import hashing
from app.models import Case, Document, Extraction
from app.prompts import extraction_prompt
from app.schemas.extraction import ExtractionResult
from app.services import claude_client, s3

logger = logging.getLogger(__name__)

# 120 days is the ORIGINAL Medicare (Part A/B) redetermination window only.
# Medicare Advantage is Part C: reconsideration runs 60 days from the organization
# determination notice (42 CFR 422.582), so it takes the 60-day default and must NOT
# be bucketed with Original Medicare — that would show a deadline 60 days too late.
_MEDICARE_PLANS = {"medicare"}
_MEDICARE_ADVANTAGE_PLANS = {"medicare_advantage"}
_MEDICAID_PLANS = {"medicaid", "medicaid_mco"}


def _appeal_deadline(denial_date: date | None, plan_type: str) -> date | None:
    if denial_date is None:
        return None
    days = 120 if plan_type in _MEDICARE_PLANS else 60
    return denial_date + timedelta(days=days)


def deadline_note(plan_type: str | None) -> str:
    """Human-facing caveat about the ESTIMATED appeal deadline. The deadline is
    computed conservatively from the denial date; the payer's actual filing
    deadline governs and is the practice's responsibility to confirm."""
    base = (
        "This deadline is an estimate from the denial date — confirm the exact "
        "filing deadline in the payer's policy before relying on it."
    )
    if plan_type in _MEDICARE_ADVANTAGE_PLANS:
        return (
            "Medicare Advantage (Part C) plans allow 60 days from the organization "
            "determination notice — not the 120-day Original Medicare window. Confirm "
            "the exact window with the plan. " + base
        )
    if plan_type in _MEDICAID_PLANS:
        return (
            "Medicaid appeal deadlines are state-specific and are often shorter than "
            "the 60-day default shown here. " + base
        )
    if plan_type in ("unknown", "other") or plan_type is None:
        return (
            "The payer type wasn't confirmed, so the conservative 60-day default is used. " + base
        )
    return base


async def _read_extracted_text(session: AsyncSession, case: Case) -> dict[str, str]:
    """Map doc_type -> extracted text (from the .extracted.txt sibling in S3)."""
    documents = (await session.scalars(select(Document).where(Document.case_id == case.id))).all()
    texts: dict[str, str] = {}
    for doc in documents:
        key = s3.extracted_text_key(doc.s3_key)
        raw = await run_in_threadpool(s3.get_bytes, key)
        texts[doc.doc_type] = raw.decode("utf-8", errors="replace")
    return texts


async def run_ai_extraction(session: AsyncSession, case: Case) -> Extraction:
    """Run the extraction model over the three documents, then persist the
    extractions row and denormalize key fields onto the case."""
    texts = await _read_extracted_text(session, case)
    user_prompt = extraction_prompt.build_user_prompt(
        texts.get("denial", ""), texts.get("claim", ""), texts.get("clinical", "")
    )

    outcome = await claude_client.complete_json(
        case_id=case.id,
        purpose="extraction",
        prompt_version=extraction_prompt.VERSION,
        system=extraction_prompt.SYSTEM,
        user_prompt=user_prompt,
        schema=ExtractionResult,
    )
    result: ExtractionResult = outcome.data

    # PHI minimization: keyed-hash the member id, and never persist the raw value.
    #
    # HMAC, not a bare digest. Member IDs are short, structured and payer-prefixed,
    # so a plain SHA-256 is exhaustible offline — anyone with a DB dump recovers the
    # raw identifiers, which means the hash was not a de-identification control at
    # all. The practice id is mixed in as scope so an identical member across two
    # practices does not produce an identical hash, which would otherwise prove the
    # link and defeat tenant isolation.
    #
    # Degrades to NULL rather than failing the pipeline when no pepper is
    # configured: this column currently has no readers, so a missing value costs
    # nothing, while a weak value would look identical in the database and provide
    # none of the protection.
    member_id_hash = None
    if result.member_id:
        if hashing.is_configured():
            member_id_hash = hashing.keyed_hash(
                result.member_id,
                purpose=hashing.MEMBER_ID,
                scope=str(case.practice_id),
            )
        else:
            logger.warning(
                "member_id_hash omitted: PHI_HASH_PEPPER is not configured",
                extra={"context": {"case_id": str(case.id)}},
            )
    confidence = (
        Decimal(str(round(result.confidence, 2))) if result.confidence is not None else None
    )

    extraction = Extraction(
        case_id=case.id,
        payer_name=result.payer_name,
        plan_type=result.plan_type,
        claim_number=result.claim_number,
        carc_codes=result.carc_codes,
        rarc_codes=result.rarc_codes,
        group_codes=result.group_codes,
        cpt_codes=result.cpt_codes,
        icd10_codes=result.icd10_codes,
        modifiers=result.modifiers,
        pos_codes=result.pos_codes,
        denial_date=result.denial_date,
        date_of_service=result.date_of_service,
        billed_amount_cents=result.billed_amount_cents,
        denied_amount_cents=result.denied_amount_cents,
        # exclude raw member_id from the archived JSON
        extracted_json=result.model_dump(mode="json", exclude={"member_id"}),
        confidence=confidence,
        model_run_id=outcome.model_run_id,
    )
    session.add(extraction)

    case.payer_name = result.payer_name
    case.plan_type = result.plan_type
    case.claim_number = result.claim_number
    case.member_id_hash = member_id_hash
    case.patient_initials = result.patient_initials
    case.date_of_service = result.date_of_service
    case.denial_date = result.denial_date
    case.appeal_deadline = _appeal_deadline(result.denial_date, result.plan_type)
    case.billed_amount_cents = result.billed_amount_cents
    case.denied_amount_cents = result.denied_amount_cents

    await session.flush()
    logger.info(
        "ai extraction complete",
        extra={
            "context": {
                "case_id": str(case.id),
                "carc": result.carc_codes,
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
            }
        },
    )
    return extraction
