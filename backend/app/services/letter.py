import logging
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Analysis, AppealLetter, Case, Extraction, Practice
from app.prompts import letter_prompt
from app.schemas.letter import LetterDraft
from app.services import claude_client
from app.services.analysis import read_clinical_text, read_supplemental_text

logger = logging.getLogger(__name__)


def should_draft_letter(analysis: Analysis | None) -> bool:
    """Only appealable cases get a letter. A missing analysis or is_appealable
    false -> skip drafting (the case still transitions to ready)."""
    return analysis is not None and analysis.is_appealable


def next_letter_version(existing_versions: list[int]) -> int:
    """Letters are versioned per case; re-analysis adds version=2, etc."""
    return max(existing_versions, default=0) + 1


def format_amount_cents(cents: int | None) -> str:
    """Render integer cents as a USD string for the letter (display only).

    Integer divmod rather than `cents / 100` — hard rule 11 forbids floats for
    currency, and a float division is the exact shape of the bug the rule exists to
    prevent, even where the magnitudes involved happen to round correctly."""
    if cents is None:
        return "the denied amount"
    sign = "-" if cents < 0 else ""
    dollars, remainder = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{remainder:02d}"


def _letterhead(case: Case, practice: Practice | None, extraction: Extraction | None) -> dict:
    addr = None
    if practice is not None:
        parts = [practice.address_line1, practice.address_line2]
        city_line = ", ".join(p for p in [practice.city, practice.state] if p)
        if city_line or practice.zip:
            parts.append(" ".join(p for p in [city_line, practice.zip] if p))
        addr = "\n".join(p for p in parts if p) or None
    return {
        "letter_date": date.today(),
        "practice_name": practice.name if practice else None,
        "npi": practice.npi if practice else None,
        "tax_id": practice.tax_id if practice else None,
        "address": addr,
        "payer_name": case.payer_name,
        "patient_initials": case.patient_initials,
        "claim_number": case.claim_number or (extraction.claim_number if extraction else None),
        "date_of_service": case.date_of_service,
        "denial_date": case.denial_date,
        "denied_amount": format_amount_cents(case.denied_amount_cents),
        "billed_amount": format_amount_cents(case.billed_amount_cents),
    }


async def _archive_existing_drafts(session: AsyncSession, case: Case) -> int:
    """Mark every non-archived letter on this case `archived`. Returns the count."""
    result = await session.execute(
        update(AppealLetter)
        .where(AppealLetter.case_id == case.id, AppealLetter.status != "archived")
        .values(status="archived")
    )
    return result.rowcount or 0


async def run_appeal_letter(session: AsyncSession, case: Case) -> AppealLetter | None:
    """Draft the appeal letter for an appealable case and transition the case to
    `ready`. If the latest analysis says the denial is not appealable, skip
    drafting (no empty letter) and still mark the case ready."""
    analysis = await session.scalar(
        select(Analysis).where(Analysis.case_id == case.id).order_by(Analysis.created_at.desc())
    )

    if not should_draft_letter(analysis):
        # A re-analysis can flip an appealable case to not-appealable. Any draft
        # from the earlier run is now retracted advice, so archive it rather than
        # leaving it downloadable — a practice must not be able to mail an appeal
        # the system has since withdrawn.
        await _archive_existing_drafts(session, case)
        case.status = "ready"
        await session.flush()
        logger.info(
            "letter skipped (not appealable)",
            extra={"context": {"case_id": str(case.id)}},
        )
        return None

    extraction = await session.scalar(
        select(Extraction)
        .where(Extraction.case_id == case.id)
        .order_by(Extraction.created_at.desc())
    )
    practice = await session.get(Practice, case.practice_id)
    clinical_text = await read_clinical_text(session, case)
    supplemental_text = await read_supplemental_text(session, case)

    analysis_json = {
        "denial_category": analysis.denial_category,
        "is_appealable": analysis.is_appealable,
        "appealability_reason": analysis.appealability_reason,
        "recommended_appeal_level": analysis.recommended_appeal_level,
        "success_probability": (
            float(analysis.success_probability)
            if analysis.success_probability is not None
            else None
        ),
    }
    user_prompt = letter_prompt.build_user_prompt(
        _letterhead(case, practice, extraction),
        extraction.extracted_json if extraction else {},
        analysis_json,
        clinical_text,
        supplemental_text,
        appeal_level=analysis.recommended_appeal_level or "level_1_internal",
    )

    outcome = await claude_client.complete_json(
        case_id=case.id,
        purpose="letter_draft",
        prompt_version=letter_prompt.VERSION,
        system=letter_prompt.SYSTEM,
        user_prompt=user_prompt,
        schema=LetterDraft,
        max_tokens=3000,
    )
    draft: LetterDraft = outcome.data

    # Belt and braces behind the schema's min_length. If an empty body ever reaches
    # here the case must NOT go `ready` — that is precisely the empty success state
    # hard rule 9 forbids, and the UI would render an active Download button that
    # 404s. Raise instead and let the pipeline mark the case `error`.
    if not draft.body.strip():
        raise ValueError("letter draft has an empty body")

    # A new draft supersedes any previous one (re-analysis, retry).
    await _archive_existing_drafts(session, case)

    existing = list(
        await session.scalars(select(AppealLetter.version).where(AppealLetter.case_id == case.id))
    )
    letter = AppealLetter(
        case_id=case.id,
        version=next_letter_version(existing),
        body=draft.body,
        appeal_type=draft.appeal_type,
        status="draft",
        model_run_id=outcome.model_run_id,
    )
    session.add(letter)
    case.status = "ready"
    await session.flush()
    logger.info(
        "appeal letter drafted",
        extra={
            "context": {
                "case_id": str(case.id),
                "letter_id": str(letter.id),
                "version": letter.version,
                "appeal_type": letter.appeal_type,
                "body_chars": len(draft.body),
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
            }
        },
    )
    return letter
