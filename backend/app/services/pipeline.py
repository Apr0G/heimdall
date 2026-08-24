import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.session import AsyncSessionLocal
from app.models import Case, Document
from app.services import document_extractor, s3
from app.services.analysis import run_ai_analysis
from app.services.extraction import run_ai_extraction
from app.services.letter import run_appeal_letter
from app.services.precheck import run_precheck_extraction, run_risk_report

logger = logging.getLogger(__name__)


async def _run_phase(case_id: UUID, run_id: UUID, phase, **kwargs) -> bool:
    """Run one pipeline phase in its own short-lived session, so a pooled DB
    connection is not held across the whole multi-minute pipeline (three Bedrock
    calls + Textract). State persists to the DB between phases, so each phase
    re-fetches the case fresh.

    Returns False (and does nothing) if a newer run has claimed the case — the
    caller stops the sequence. This is the anti-duplicate guard: a stall-detection
    retry stamps a new pipeline_run_id, so the older runner aborts here.

    Ownership is checked twice, and the second check is the one that matters. A
    phase runs for minutes (Textract + Bedrock), and a retry can land in that
    window; committing then would write this run's stale results over the newer
    run's. The re-check takes the case row FOR UPDATE, so re-reading the token and
    committing are one critical section — the lock is held for that instant only,
    never across the phase itself."""
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
        current = await session.scalar(
            select(Case.pipeline_run_id).where(Case.id == case_id).with_for_update()
        )
        if current != run_id:
            await session.rollback()
            logger.info(
                "pipeline superseded mid-phase, discarding this run's results",
                extra={"context": {"case_id": str(case_id)}},
            )
            return False
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
            await _touch_if_owner(case_id=case_id, run_id=run_id)
            if not await _run_phase(case_id, run_id, phase, **kwargs):
                return
    except Exception as exc:
        await _mark_error(case_id, run_id, exc)


async def run_precheck_pipeline(case_id: UUID, run_id: UUID) -> None:
    """Pre-check orchestrator (draft claim + clinical notes → risk report):
    document extraction -> claim-line extraction (Bedrock) -> deterministic
    NCCI pass + documentation review (Bedrock) -> risk_reports row and the
    final transition to `ready` (run_risk_report sets it — the pre-check
    pipeline has no letter phase, and a pipeline that never sets `ready`
    strands every case at the stall detector).

    Same session/ownership/error discipline as run_full_pipeline."""
    if not await _owns_case(case_id, run_id):
        return

    phases = (
        (_extract_documents, {"only_missing_text": True}),
        (run_precheck_extraction, {}),
        (run_risk_report, {}),
    )
    try:
        for phase, kwargs in phases:
            await _touch_if_owner(case_id=case_id, run_id=run_id)
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
            await _touch_if_owner(case_id=case_id, run_id=run_id)
            if not await _run_phase(case_id, run_id, phase, **kwargs):
                return
    except Exception as exc:
        await _mark_error(case_id, run_id, exc)


class DocumentTamperedError(RuntimeError):
    """A document's bytes no longer match the content_hash recorded at first read."""


async def _extract_one(session: AsyncSession, doc: Document, *, case_id, run_id) -> None:
    # Read the PDF once: hash it for an integrity anchor (§164.312(c)(1)) and reuse
    # the same bytes for digital-text extraction (no second S3 read).
    data = await run_in_threadpool(s3.get_bytes, doc.s3_key)
    digest = hashlib.sha256(data).hexdigest()
    if doc.content_hash is None:
        # First read establishes the anchor.
        doc.content_hash = digest
    elif doc.content_hash != digest:
        # Do NOT re-bless. Overwriting the hash unconditionally on every run meant
        # any retry silently re-anchored a tampered object, so the integrity check
        # would compare it against the tampered bytes and report a match forever.
        raise DocumentTamperedError(
            f"document {doc.id} no longer matches its recorded content hash"
        )
    text = await run_in_threadpool(document_extractor.digital_text_from_bytes, data)
    if text is None:
        # Scanned PDF -> OCR. Mark pending so the state is observable — via a
        # guarded UPDATE in its own session, never a commit of THIS session,
        # which would bypass _run_phase's ownership re-check (a superseded run
        # must not write anything into the newer run's case).
        await _touch_if_owner(
            case_id=case_id, run_id=run_id, document_id=doc.id, ocr_status="pending"
        )
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
        if only_missing_text and doc.content_hash is not None:
            # Skip docs already extracted on the first pass; only do the new ones.
            #
            # Keyed on content_hash, NOT on S3 presence alone. A superseded run can
            # write the extracted text to S3 and then have its DB transaction rolled
            # back, discarding content_hash — after which an S3-presence check would
            # skip that document forever, leaving it permanently unhashed and so
            # permanently invisible to the integrity check.
            existing = await run_in_threadpool(s3.head_object, s3.extracted_text_key(doc.s3_key))
            if existing is not None:
                continue
        await _extract_one(session, doc, case_id=case.id, run_id=case.pipeline_run_id)
        # Heartbeat. A case whose row hasn't advanced in STALE_PROCESSING minutes is
        # treated as stalled and eligible for a concurrent retry — but a healthy
        # multi-document Textract run can legitimately exceed that window. Touching
        # the case row between documents keeps a working pipeline from being
        # declared dead and duplicated.
        case.updated_at = datetime.now(UTC)
        await session.flush()


async def _touch_if_owner(
    *, case_id: UUID, run_id: UUID, document_id: UUID | None = None, ocr_status: str | None = None
) -> None:
    """Heartbeat the case row (and optionally one document's ocr_status) in a
    separate short transaction, only if this run still owns the case. Used
    mid-phase so a long Textract or Bedrock stretch doesn't trip the stall
    detector (STALE_PROCESSING) and trigger a duplicate, paid-for run."""
    async with AsyncSessionLocal() as session:
        owned = await session.scalar(
            update(Case)
            .where(Case.id == case_id, Case.pipeline_run_id == run_id)
            .values(updated_at=datetime.now(UTC))
            .returning(Case.id)
        )
        if owned is not None and document_id is not None and ocr_status is not None:
            await session.execute(
                update(Document).where(Document.id == document_id).values(ocr_status=ocr_status)
            )
        await session.commit()


async def _mark_error(case_id: UUID, run_id: UUID, exc: Exception) -> None:
    # Own session: the failed phase's session already rolled back on exit. The
    # ownership test is the UPDATE's WHERE rather than a read-then-write, so a
    # retry landing in between cannot have its fresh `processing` overwritten with
    # this dead run's `error`.
    # Exception type + AWS error code only (both safe enums like "NoSuchKey")
    # — never the raw message, which could echo a key or path.
    detail = type(exc).__name__
    response = getattr(exc, "response", None)
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    message = f"Processing failed ({detail}{f': {code}' if code else ''})."
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Case)
            .where(Case.id == case_id, Case.pipeline_run_id == run_id)
            .values(status="error", error_message=message)
        )
        await session.commit()
    logger.exception("pipeline failed", extra={"context": {"case_id": str(case_id)}})
