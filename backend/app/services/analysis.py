import logging
import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models import Analysis, Case, Document, Extraction
from app.prompts import analysis_prompt
from app.schemas.analysis import AnalysisResult
from app.services import claude_client, s3

logger = logging.getLogger(__name__)


def probability_band(probability: float | None) -> str | None:
    """Spec thresholds: low < 0.35, moderate 0.35-0.65, high > 0.65.

    Returns None when the model gave no estimate — the band is a *derived* fact, so
    inventing "moderate" from a missing input showed the doctor a confidence level
    that was never produced."""
    if probability is None:
        return None
    if probability < 0.35:
        return "low"
    if probability <= 0.65:
        return "moderate"
    return "high"


# Conditional documents a doctor can add after the first review (Phase 12).
SUPPLEMENTAL_DOC_TYPES = ("prior_auth", "prior_treatment")

# Denials that are never appealable, enforced server-side rather than trusted from
# model output. CO-45 is a contracted write-off and PR-* means the patient owes —
# in both cases there is no payer obligation to appeal against.
#
# CO-97 is deliberately ABSENT: whether an NCCI bundling edit is overridable turns
# on the PTP modifier indicator, which lives in the CMS edit tables and never
# appears on an EOB or CMS-1500. Auto-classifying it as never-appeal silently drops
# winnable indicator-1 appeals, so it stays appealable and flagged for review.
_NEVER_APPEAL_EXACT = {"CO-45"}
_NEVER_APPEAL_PREFIXES = ("PR-",)


_CARC_RE = re.compile(r"^\s*(?:([A-Z]{2})\s*[-_ ]?\s*)?(\d{1,3})\s*$")


def _canonical_carcs(raw: str, group_codes: list[str]) -> list[str]:
    """Every GROUP-REASON spelling a raw code could mean, in the form the guard
    matches ("CO-45"). Accepts "CO-45", "co 45", "CO45", "CO_45"; a bare reason
    code ("45") is combined with each supplied group code, since extraction may
    split the pair across `carc_codes` / `group_codes`. Unparseable → []."""
    m = _CARC_RE.match(raw.upper())
    if not m:
        return []
    group, reason = m.group(1), m.group(2)
    if group:
        return [f"{group}-{reason}"]
    groups = [g.strip().upper() for g in group_codes if isinstance(g, str) and g.strip()]
    return [f"{g}-{reason}" for g in groups]


def never_appealable_codes(
    carc_codes: list[str] | None, group_codes: list[str] | None = None
) -> list[str]:
    """The subset of `carc_codes` that are categorically not appealable, in
    canonical form. Pure, so it is unit-testable without a database or a model
    call. Spelling-tolerant on purpose: this is the control and the prompt is
    the request, and a guard that recognises one spelling fails open."""
    if not carc_codes:
        return []
    hits: list[str] = []
    for raw in carc_codes:
        if not isinstance(raw, str):
            continue
        for code in _canonical_carcs(raw, group_codes or []):
            if code in hits:
                continue
            if code in _NEVER_APPEAL_EXACT or code.startswith(_NEVER_APPEAL_PREFIXES):
                hits.append(code)
    return hits


async def _read_doc_text(session: AsyncSession, doc: Document) -> str:
    raw = await run_in_threadpool(s3.get_bytes, s3.extracted_text_key(doc.s3_key))
    return raw.decode("utf-8", errors="replace")


async def read_clinical_text(session: AsyncSession, case: Case) -> str:
    doc = await session.scalar(
        select(Document).where(Document.case_id == case.id, Document.doc_type == "clinical")
    )
    if doc is None:
        return ""
    return await _read_doc_text(session, doc)


async def read_supplemental_text(session: AsyncSession, case: Case) -> str:
    """Concatenate the text of any conditional documents the doctor added after
    the first review (prior auth, prior treatment), each labeled by type."""
    docs = (
        await session.scalars(
            select(Document)
            .where(
                Document.case_id == case.id,
                Document.doc_type.in_(SUPPLEMENTAL_DOC_TYPES),
            )
            .order_by(Document.uploaded_at.asc())
        )
    ).all()
    sections = []
    for doc in docs:
        text = await _read_doc_text(session, doc)
        if text.strip():
            sections.append(f"[{doc.doc_type.upper()}]\n{text.strip()}")
    return "\n\n".join(sections)


async def run_ai_analysis(session: AsyncSession, case: Case) -> Analysis:
    """Classify the denial, judge appealability, estimate success, and persist
    the analyses row. The probability band is derived server-side from the
    estimate so it always matches the documented thresholds."""
    extraction = await session.scalar(
        select(Extraction)
        .where(Extraction.case_id == case.id)
        .order_by(Extraction.created_at.desc())
    )
    clinical_text = await read_clinical_text(session, case)
    supplemental_text = await read_supplemental_text(session, case)
    user_prompt = analysis_prompt.build_user_prompt(
        extraction.extracted_json if extraction else {},
        clinical_text,
        supplemental_text,
    )

    outcome = await claude_client.complete_json(
        case_id=case.id,
        purpose="analysis",
        prompt_version=analysis_prompt.VERSION,
        system=analysis_prompt.SYSTEM,
        user_prompt=user_prompt,
        schema=AnalysisResult,
    )
    result: AnalysisResult = outcome.data

    success_probability = (
        Decimal(str(round(result.success_probability, 3)))
        if result.success_probability is not None
        else None
    )

    # Server-side never-appeal guard. The triage rules live in the prompt, which
    # makes them a request rather than a control — a model that flips a PR-1 to
    # appealable would otherwise draft an appeal for a balance the patient owes.
    # The CARC codes are already on the extraction, so this is checkable without
    # trusting the model. Same pattern as probability_band: derive, don't accept.
    blocking_codes = never_appealable_codes(
        extraction.carc_codes if extraction else [],
        extraction.group_codes if extraction else [],
    )
    is_appealable = result.is_appealable and not blocking_codes
    appealability_reason = result.appealability_reason
    if blocking_codes and result.is_appealable:
        logger.warning(
            "never-appeal guard overrode model output",
            extra={
                "context": {
                    "case_id": str(case.id),
                    "codes": blocking_codes,
                    "model_said": result.is_appealable,
                }
            },
        )
        appealability_reason = (
            f"{', '.join(blocking_codes)} is a categorically non-appealable adjustment "
            "(contractual write-off or patient responsibility), so no payer appeal "
            "applies. The AI assessment disagreed and was overridden."
        )

    analysis = Analysis(
        case_id=case.id,
        denial_category=result.denial_category,
        is_appealable=is_appealable,
        appealability_reason=appealability_reason,
        success_probability=success_probability,
        probability_band=probability_band(result.success_probability),
        reasoning_text=result.reasoning_text,
        recommended_appeal_level=result.recommended_appeal_level,
        additional_documents_needed=[d for d in result.additional_documents_needed if d != "none"],
        model_run_id=outcome.model_run_id,
    )
    session.add(analysis)
    await session.flush()
    logger.info(
        "ai analysis complete",
        extra={
            "context": {
                "case_id": str(case.id),
                "denial_category": result.denial_category,
                "is_appealable": is_appealable,
                "band": analysis.probability_band,
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
            }
        },
    )
    return analysis
