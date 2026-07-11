import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.session import AsyncSessionLocal
from app.models import Case, Document
from app.services import document_extractor, s3
from app.services.analysis import run_ai_analysis
from app.services.extraction import run_ai_extraction
from app.services.letter import run_appeal_letter

logger = logging.getLogger(__name__)


async def _run_phase(case_id: UUID, run_id: UUID, phase, **kwargs) -> bool:
    """Run one pipeline phase in its own short-lived session, so a pooled DB
    connection is not held across the whole multi-minute pipeline (three Bedrock
    calls + Textract). State persists to the DB between phases, so each phase
    re-fetches the case fresh.

    Returns False (and does nothing) if a newer run has claimed the case — the
    caller stops the sequence. This is the anti-duplicate guard: a stall-detection
    retry stamps a new pipeline_run_id, so the older runner aborts here."""
    async with AsyncSessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            raise RuntimeError(f"case {case_id} vanished mid-pipeline")
        if case.pipeline_run_id != run_id:
            logger.info(
                "pipeline superseded by a newer run, aborting",
                extra={"context": {"case_id": str(case_id)}},
            )
            return False
        await phase(session, case, **kwargs)
        await session.commit()
        return True


async def _owns_case(case_id: UUID, run_id: UUID) -> bool:
    async with AsyncSessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            logger.warning("pipeline: case not found", extra={"context": {"case_id": str(case_id)}})
            return False
        return case.pipeline_run_id == run_id


async def run_full_pipeline(case_id: UUID, run_id: UUID) -> None:
    """Background orchestrator for a case: document extraction (embedded text via
    pypdf, OCR via Textract for scanned PDFs) -> AI extraction -> analysis ->
    letter draft -> the final transition to `ready`. Each phase runs in its own
    session (see _run_phase) and aborts if a newer run supersedes this one.

    Extraction uses only_missing_text=True so a retry after a later-phase failure
    reuses already-extracted text instead of re-paying Textract + the extraction
    model (on a fresh case nothing is extracted yet, so it still does all three).

    No silent failures: any error sets case.status='error' with a PHI-free
    error_message. Never logs document text — only ids, lengths, and statuses.
    """
    if not await _owns_case(case_id, run_id):
        return

    phases = (
        (_extract_documents, {"only_missing_text": True}),
        (run_ai_extraction, {}),
        (run_ai_analysis, {}),
        (run_appeal_letter, {}),
    )
    try:
        for phase, kwargs in phases:
            if not await _run_phase(case_id, run_id, phase, **kwargs):
                return
    except Exception as exc:
        await _mark_error(case_id, run_id, exc)


async def run_reanalysis(case_id: UUID, run_id: UUID) -> None:
    """Re-run analysis + letter after the doctor adds conditional documents
    (Phase 12). Extracts text from the newly added docs, re-analyzes with the
    fuller picture, and drafts the next letter version, ending at `ready`. Each
    phase runs in its own session and aborts if superseded (see _run_phase)."""
    if not await _owns_case(case_id, run_id):
        return

    phases = (
        (_extract_documents, {"only_missing_text": True}),
        (run_ai_analysis, {}),
        (run_appeal_letter, {}),
    )
    try:
        for phase, kwargs in phases:
            if not await _run_phase(case_id, run_id, phase, **kwargs):
                return
    except Exception as exc:
        await _mark_error(case_id, run_id, exc)


async def _extract_one(session: AsyncSession, doc: Document) -> None:
    # Read the PDF once: hash it for an integrity anchor (§164.312(c)(1)) and reuse
    # the same bytes for digital-text extraction (no second S3 read).
    data = await run_in_threadpool(s3.get_bytes, doc.s3_key)
    doc.content_hash = hashlib.sha256(data).hexdigest()
    text = await run_in_threadpool(document_extractor.digital_text_from_bytes, data)
    if text is None:
        # Scanned PDF -> OCR. Mark pending so the state is observable.
        doc.ocr_status = "pending"
        await session.commit()
        text = await run_in_threadpool(document_extractor.run_textract, doc.s3_key)
        await run_in_threadpool(document_extractor.store_extracted_text, doc.s3_key, text)
        doc.ocr_status = "completed"
        doc.ocr_completed_at = datetime.now(UTC)
    else:
        await run_in_threadpool(document_extractor.store_extracted_text, doc.s3_key, text)
        doc.ocr_status = "not_needed"
    await session.flush()
    logger.info(
        "extracted document",
        extra={
            "context": {
                "document_id": str(doc.id),
                "chars": len(text),
                "ocr_status": doc.ocr_status,
            }
        },
    )


async def _extract_documents(
    session: AsyncSession, case: Case, *, only_missing_text: bool = False
) -> None:
    documents = (await session.scalars(select(Document).where(Document.case_id == case.id))).all()
    for doc in documents:
        if only_missing_text:
            # Skip docs already extracted on the first pass; only do the new ones.
            existing = await run_in_threadpool(s3.head_object, s3.extracted_text_key(doc.s3_key))
            if existing is not None:
                continue
        await _extract_one(session, doc)


async def _mark_error(case_id: UUID, run_id: UUID, exc: Exception) -> None:
    # Own session: the failed phase's session already rolled back on exit. Only
    # mark error if this run still owns the case — a superseding run owns the state.
    async with AsyncSessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is not None and case.pipeline_run_id == run_id:
            case.status = "error"
            # Exception type + AWS error code only (both safe enums like "NoSuchKey")
            # — never the raw message, which could echo a key or path.
            detail = type(exc).__name__
            response = getattr(exc, "response", None)
            code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
            case.error_message = f"Processing failed ({detail}{f': {code}' if code else ''})."
            await session.commit()
    logger.exception("pipeline failed", extra={"context": {"case_id": str(case_id)}})
