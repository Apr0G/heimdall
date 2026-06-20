import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models import Analysis, Case, Document, Extraction
from app.prompts import analysis_prompt
from app.schemas.analysis import AnalysisResult
from app.services import claude_client, s3

logger = logging.getLogger(__name__)


def probability_band(probability: float | None) -> str:
    """Spec thresholds: low < 0.35, moderate 0.35-0.65, high > 0.65."""
    if probability is None:
        return "moderate"
    if probability < 0.35:
        return "low"
    if probability <= 0.65:
        return "moderate"
    return "high"


# Conditional documents a doctor can add after the first review (Phase 12).
SUPPLEMENTAL_DOC_TYPES = ("prior_auth", "prior_treatment")


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

    analysis = Analysis(
        case_id=case.id,
        denial_category=result.denial_category,
        is_appealable=result.is_appealable,
        appealability_reason=result.appealability_reason,
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
                "is_appealable": result.is_appealable,
                "band": analysis.probability_band,
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
            }
        },
    )
    return analysis
