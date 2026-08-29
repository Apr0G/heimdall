"""Turn a doctor's edit selection into a corrected claim PDF.

Bridges the risk report (what the pipeline proposed), the doctor's choices
(which of those, with which value), and the in-place patcher. The client only
ever sends *indexes* into the stored ``proposed_edits`` plus an optional value;
kind and target come from the report row, and the value is re-validated with
the same whitelist the schema uses — so nothing typed in a browser reaches the
PDF unvalidated.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models import Case, CorrectedClaim, Document, RiskReport, User
from app.schemas.precheck import normalize_edit_value
from app.services import claim_patch, s3
from app.services.claim_patch import ClaimEdit, PatchResult

logger = logging.getLogger(__name__)

# Which document the patcher edits, and the ocr_status that means it has a
# real text layer (a scan went through Textract and is `completed`).
EDITABLE_DOC_TYPE = "claim"
EDITABLE_OCR_STATUS = "not_needed"


class ClaimNotEditable(Exception):
    """The case can't produce a corrected PDF. ``code`` is one of: not_ready,
    no_report, no_claim_document, scanned, tampered."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class InvalidSelection(ValueError):
    """The request referenced an edit that doesn't exist or can't be applied.
    ``code``: index_out_of_range, duplicate_index, kind_not_applicable,
    value_required, bad_value."""

    def __init__(self, code: str, index: int | None = None) -> None:
        self.code = code
        self.index = index
        super().__init__(code if index is None else f"{code} (edit {index})")


@dataclass(frozen=True)
class Selection:
    index: int
    value: str | None = None
    remove: bool = False  # remove the whole line instead of applying the edit
    charge: str = "scale"  # change_units: "scale" the line charge with the units, or "keep"


EDITABLE_TEXT_SOURCES = ("pdf_text", "form_fields")


def _document_editable(d: Document) -> bool:
    # text_source is authoritative; rows from before 0017 have none, and for
    # those "no OCR was needed" means a text layer exists.
    if getattr(d, "text_source", None) is not None:
        return d.text_source in EDITABLE_TEXT_SOURCES
    return d.ocr_status == EDITABLE_OCR_STATUS


def claim_document_editable(documents: list[Document]) -> bool:
    """True when the draft claim can be edited in place: born-digital page text
    or a fillable form. A scan (OCR) can't."""
    return any(d.doc_type == EDITABLE_DOC_TYPE and _document_editable(d) for d in documents)


def claim_format(documents: list[Document]) -> str | None:
    """ "form" for a fillable claim, "text" for born-digital, None otherwise."""
    for d in documents:
        if d.doc_type != EDITABLE_DOC_TYPE:
            continue
        if getattr(d, "text_source", None) == "form_fields":
            return "form"
        return "text" if _document_editable(d) else None
    return None


def resolve_selections(
    proposed_edits: list[dict], selections: list[Selection]
) -> list[tuple[int, ClaimEdit]]:
    """Map client selections onto the report's edits, validating as we go.
    Pure so it can be tested without a database."""
    seen: set[int] = set()
    resolved: list[tuple[int, ClaimEdit]] = []
    for sel in selections:
        if sel.index in seen:
            raise InvalidSelection("duplicate_index", sel.index)
        seen.add(sel.index)
        if not 0 <= sel.index < len(proposed_edits):
            raise InvalidSelection("index_out_of_range", sel.index)
        edit = proposed_edits[sel.index]
        kind = str(edit.get("kind") or "")
        target = str(edit.get("target") or "").strip()
        if kind not in claim_patch.EDIT_KINDS or not target:
            # `documentation` edits are for the note, not the claim; an edit
            # without a target has nothing to point the patcher at.
            raise InvalidSelection("kind_not_applicable", sel.index)
        if sel.remove:
            kind = "remove_line"
        value: str | None = None
        if kind != "remove_line":
            raw = sel.value if sel.value is not None else edit.get("value")
            if raw is None or not str(raw).strip():
                raise InvalidSelection("value_required", sel.index)
            value = normalize_edit_value(kind, raw)
            if value is None:
                raise InvalidSelection("bad_value", sel.index)
        charge = sel.charge if sel.charge in claim_patch.CHARGE_CHOICES else "scale"
        # An NCCI unit limit is a ceiling, not a count — the report says which
        # kind (never the client), and it holds even when the doctor types a
        # different number for that finding.
        cap = edit.get("cap") if kind == "change_units" else None
        if cap not in claim_patch.CAP_KINDS:
            cap = None
        resolved.append(
            (
                sel.index,
                ClaimEdit(kind=kind, target=target, value=value, charge=charge, cap=cap),
            )
        )
    return resolved


def _result_rows(resolved: list[tuple[int, ClaimEdit]], patched: PatchResult) -> list[dict]:
    rows: list[dict] = []
    for (index, edit), outcome in zip(resolved, patched.results, strict=True):
        rows.append(
            {
                "index": index,
                "kind": edit.kind,
                "target": edit.target,
                "value": edit.value,
                "applied": outcome.applied,
                "reason": outcome.reason,
                "applied_lines": outcome.applied_lines,
                "note": outcome.note,
                "charge_before_cents": outcome.charge_before_cents,
                "charge_after_cents": outcome.charge_after_cents,
            }
        )
    return rows


async def latest_corrected_claim(session: AsyncSession, case_id: UUID) -> CorrectedClaim | None:
    return await session.scalar(
        select(CorrectedClaim)
        .where(CorrectedClaim.case_id == case_id)
        .order_by(CorrectedClaim.version.desc())
        .limit(1)
    )


async def create_corrected_claim(
    session: AsyncSession, case: Case, selections: list[Selection], user: User
) -> CorrectedClaim:
    """Patch the draft claim with the selected edits and record a new version.
    Does not commit — the router owns the transaction. Raises ClaimNotEditable,
    InvalidSelection, or claim_patch.ClaimPatchError."""
    if case.case_type != "pre_check" or case.status != "ready":
        raise ClaimNotEditable("not_ready")
    report = await session.scalar(
        select(RiskReport)
        .where(RiskReport.case_id == case.id)
        .order_by(RiskReport.created_at.desc())
        .limit(1)
    )
    if report is None:
        raise ClaimNotEditable("no_report")
    doc = await session.scalar(
        select(Document)
        .where(Document.case_id == case.id, Document.doc_type == EDITABLE_DOC_TYPE)
        .order_by(Document.uploaded_at.desc())
        .limit(1)
    )
    if doc is None:
        raise ClaimNotEditable("no_claim_document")
    if not _document_editable(doc):
        raise ClaimNotEditable("scanned")

    resolved = resolve_selections(list(report.proposed_edits or []), selections)

    data = await run_in_threadpool(s3.get_bytes, doc.s3_key)
    # Same integrity anchor as the pipeline (§164.312(c)(1)): never patch bytes
    # that no longer match what was analysed.
    if doc.content_hash and hashlib.sha256(data).hexdigest() != doc.content_hash:
        raise ClaimNotEditable("tampered")

    patched = await run_in_threadpool(claim_patch.patch_claim, data, [e for _, e in resolved])

    version = (
        await session.scalar(
            select(func.coalesce(func.max(CorrectedClaim.version), 0)).where(
                CorrectedClaim.case_id == case.id
            )
        )
        or 0
    ) + 1
    key: str | None = None
    if patched.pages_changed:
        key = s3.corrected_claim_key(case.practice_id, case.id, version)
        await run_in_threadpool(s3.put_bytes, key, patched.pdf, "application/pdf")

    row = CorrectedClaim(
        case_id=case.id,
        risk_report_id=report.id,
        version=version,
        s3_key=key,
        results=_result_rows(resolved, patched),
        total_updated=patched.total_updated,
        created_by=user.id,
    )
    session.add(row)
    await session.flush()
    logger.info(
        "corrected claim created",
        extra={
            "context": {
                "case_id": str(case.id),
                "version": version,
                "selected": len(resolved),
                "applied": sum(1 for r in patched.results if r.applied),
                "pages_changed": patched.pages_changed,
                "total_updated": patched.total_updated,
            }
        },
    )
    return row
