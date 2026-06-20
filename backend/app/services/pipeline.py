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


async def run_full_pipeline(case_id: UUID) -> None:
    """Background orchestrator for a case.

    Phase 6 implements the document-extraction step (embedded text via pypdf,
    OCR via Textract for scanned PDFs). Phases 7-9 add AI extraction ->
    analysis -> letter draft and the final transition to `ready`.

    No silent failures: any error sets case.status='error' with a PHI-free
    error_message. Never logs document text — only ids, lengths, and statuses.
    """
    async with AsyncSessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            logger.warning("pipeline: case not found", extra={"context": {"case_id": str(case_id)}})
            return
        if case.status == "ready":
            logger.info(
                "pipeline: case already ready, skipping",
                extra={"context": {"case_id": str(case_id)}},
            )
            return

        try:
            await _extract_documents(session, case)
            await session.commit()
            await run_ai_extraction(session, case)
            await session.commit()
            await run_ai_analysis(session, case)
            await session.commit()
            await run_appeal_letter(session, case)
            await session.commit()
        except Exception as exc:
            await _mark_error(session, case_id, exc)


async def run_reanalysis(case_id: UUID) -> None:
    """Re-run analysis + letter after the doctor adds conditional documents
    (Phase 12). Extracts text from the newly added docs, re-analyzes with the
    fuller picture, and drafts the next letter version, ending at `ready`."""
    async with AsyncSessionLocal() as session:
        case = await session.get(Case, case_id)
        if case is None:
            logger.warning(
                "reanalysis: case not found", extra={"context": {"case_id": str(case_id)}}
            )
            return
        try:
            await _extract_documents(session, case, only_missing_text=True)
            await session.commit()
            await run_ai_analysis(session, case)
            await session.commit()
            await run_appeal_letter(session, case)
            await session.commit()
        except Exception as exc:
            await _mark_error(session, case_id, exc)


async def _extract_one(session: AsyncSession, doc: Document) -> None:
    text = await run_in_threadpool(document_extractor.extract_digital_text, doc.s3_key)
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


async def _mark_error(session: AsyncSession, case_id: UUID, exc: Exception) -> None:
    await session.rollback()
    case = await session.get(Case, case_id)
    if case is not None:
        case.status = "error"
        # Exception type only — never the message (could echo a key or path).
        case.error_message = f"Processing failed ({type(exc).__name__})."
        await session.commit()
    logger.exception("pipeline failed", extra={"context": {"case_id": str(case_id)}})
