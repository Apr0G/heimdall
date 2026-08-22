from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt

# These mirror the Postgres `outcome_result`, `outcome_action` and `case_status`
# enums. Typed as Literal so Pydantic rejects a bad value with a 422 AT THE
# BOUNDARY. Passing an unchecked string through to a native enum column raises
# DataError at commit — a 500, not a 400 — and in the outcome case it rolls back
# the audit row written moments earlier, so the failed attempt leaves no trace.
OutcomeResult = Literal["overturned", "upheld", "partial", "pending", "withdrawn"]
OutcomeAction = Literal["appealed", "not_appealed", "pending"]
CaseStatusFilter = Literal["draft", "processing", "ready", "submitted", "resolved", "error"]


class CaseListItem(BaseModel):
    id: UUID
    status: str
    patient_initials: str | None
    payer_name: str | None
    plan_type: str
    claim_number: str | None
    date_of_service: date | None
    denial_date: date | None
    appeal_deadline: date | None
    billed_amount_cents: int | None
    denied_amount_cents: int | None
    currency: str

    # Denormalized from the latest extraction / analysis for dashboard display.
    carc_codes: list[str]
    denial_category: str | None
    is_appealable: bool | None
    probability_band: str | None

    # Present once an outcome has been reported.
    outcome_result: str | None
    amount_recovered_cents: int | None


class CaseListResponse(BaseModel):
    items: list[CaseListItem]
    total: int
    page: int
    page_size: int


class UploadSlotRequest(BaseModel):
    doc_type: str
    filename: str
    content_type: str = "application/pdf"


class UploadUrlsRequest(BaseModel):
    documents: list[UploadSlotRequest]


class UploadSlot(BaseModel):
    doc_type: str
    s3_key: str
    upload_url: str


class UploadUrlsResponse(BaseModel):
    uploads: list[UploadSlot]


class NewCaseDocument(BaseModel):
    doc_type: str
    s3_key: str
    filename: str


class CreateCaseRequest(BaseModel):
    documents: list[NewCaseDocument]


class CreateCaseResponse(BaseModel):
    id: UUID
    status: str


class ReanalyzeRequest(BaseModel):
    """Conditional documents to add before re-running analysis + letter (Phase 12)."""

    documents: list[NewCaseDocument]


# ---- Case detail (Phase 10) ----


class DocumentDetail(BaseModel):
    id: UUID
    doc_type: str
    original_filename: str | None
    file_size_bytes: int | None
    ocr_status: str


class ExtractionDetail(BaseModel):
    payer_name: str | None
    plan_type: str | None
    claim_number: str | None
    carc_codes: list[str]
    rarc_codes: list[str]
    group_codes: list[str]
    cpt_codes: list[str]
    icd10_codes: list[str]
    modifiers: list[str]
    pos_codes: list[str]
    billed_amount_cents: int | None
    denied_amount_cents: int | None
    confidence: float | None


class AnalysisDetail(BaseModel):
    denial_category: str | None
    is_appealable: bool
    appealability_reason: str | None
    success_probability: float | None
    probability_band: str | None
    reasoning_text: str | None
    recommended_appeal_level: str | None
    additional_documents_needed: list[str]


class LetterDetail(BaseModel):
    id: UUID
    version: int
    status: str
    appeal_type: str | None
    body: str | None
    created_at: datetime


class OutcomeDetail(BaseModel):
    action_taken: str | None
    result: str | None
    amount_recovered_cents: int | None
    resolution_date: date | None
    notes: str | None
    reported_at: datetime


class CaseDetailResponse(BaseModel):
    id: UUID
    status: str
    # True when a `processing` case has stalled (pipeline killed) and can be retried.
    stalled: bool = False
    error_message: str | None
    patient_initials: str | None
    payer_name: str | None
    plan_type: str
    claim_number: str | None
    date_of_service: date | None
    denial_date: date | None
    appeal_deadline: date | None
    billed_amount_cents: int | None
    denied_amount_cents: int | None
    currency: str
    # Caveat that the appeal_deadline is an estimate (stronger for Medicaid/unknown).
    deadline_note: str | None = None

    documents: list[DocumentDetail]
    extraction: ExtractionDetail | None
    analysis: AnalysisDetail | None
    letter: LetterDetail | None  # latest version (convenience)
    letters: list[LetterDetail]  # all versions, newest first
    outcome: OutcomeDetail | None


class CaseStatusResponse(BaseModel):
    id: UUID
    status: str


class CaseStatusPollResponse(BaseModel):
    # PHI-free shape for the detail page's processing poll (no audit needed).
    id: UUID
    status: str
    stalled: bool = False


class ProcessingIdsResponse(BaseModel):
    # PHI-free feed for the background "is anything done yet?" poll.
    ids: list[UUID]


class OutcomeRequest(BaseModel):
    result: OutcomeResult
    action_taken: OutcomeAction = "appealed"
    # Non-negative integer cents (defense in depth over the client-side check).
    # Strict: lax `int` would truncate 450.0 (dollars) to 450 cents silently —
    # the same 100x unit error the extraction schema rejects.
    amount_recovered_cents: StrictInt | None = Field(default=None, ge=0)
    resolution_date: date | None = None
    notes: str | None = None


class DownloadUrlResponse(BaseModel):
    url: str


# ---- Dashboard summary / flywheel (Phase 11) ----


class PendingOutcomeItem(BaseModel):
    id: UUID
    patient_initials: str | None
    payer_name: str | None
    denied_amount_cents: int | None
    currency: str
    submitted_days_ago: int


class CaseSummaryResponse(BaseModel):
    month_case_count: int
    resolved_count: int
    win_count: int
    win_rate: float | None
    total_recovered_cents: int
    pending_outcomes: list[PendingOutcomeItem]
