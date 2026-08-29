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
CaseType = Literal["appeal", "pre_check"]


class CaseListItem(BaseModel):
    id: UUID
    status: str
    case_type: str = "appeal"
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

    # Pre-check cases only: the latest risk report's headline band.
    overall_risk_band: str | None = None


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
    # Which document set is required: appeal = denial+claim+clinical,
    # pre_check = claim+clinical. Ignored by the supplemental-upload endpoint.
    case_type: CaseType = "appeal"


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
    case_type: CaseType = "appeal"


class CreateCaseResponse(BaseModel):
    id: UUID
    status: str


class ReanalyzeRequest(BaseModel):
    """Conditional documents to add before re-running analysis + letter (Phase 12)."""

    documents: list[NewCaseDocument]


# ---- Case detail (Phase 10) ----


class DocumentDetail(BaseModel):
    """`text_source`: pdf_text | ocr | form_fields (fillable form); None for
    documents extracted before it was recorded."""

    id: UUID
    doc_type: str
    original_filename: str | None
    file_size_bytes: int | None
    ocr_status: str
    text_source: str | None = None


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


class RiskFindingDetail(BaseModel):
    """One flag in a pre-check risk report. Stored as JSONB on risk_reports;
    validated strictly at write time (schemas/precheck.py), leniently here."""

    check_id: str
    severity: str  # high | medium | low | info
    title: str
    predicted_carc: str | None = None
    explanation: str | None = None
    suggested_fix: str | None = None
    source: str  # "ncci" (deterministic) | "model" (documentation review)


class ProposedEditDetail(BaseModel):
    kind: str  # remove_line | add_modifier | change_units | change_code | documentation
    target: str | None = None
    instruction: str
    # New modifier / units / code the edit writes; None when the biller chooses.
    value: str | None = None
    # change_units from the NCCI engine: `value` is a ceiling per line ("line",
    # MUE MAI 1) or per day across the code's lines ("day", MAI 2/3), never a
    # count to raise a line to. None for a review edit.
    cap: str | None = None
    source: str  # "ncci" | "model"


class RiskReportDetail(BaseModel):
    overall_risk_band: str | None
    findings: list[RiskFindingDetail]
    proposed_edits: list[ProposedEditDetail] = []
    deterministic_count: int
    model_count: int
    # Which NCCI load served the deterministic pass; None = tables not loaded,
    # NCCI checks skipped (the report says so via an info finding).
    ncci_version_tag: str | None
    created_at: datetime


class CorrectedClaimSelection(BaseModel):
    """One chosen edit: its index in risk_report.proposed_edits, plus the value
    to write when the doctor picked one (a modifier, a unit count, a code).
    Kind and target are never client-supplied — they come from the report."""

    index: int = Field(ge=0, le=99)
    value: str | None = Field(default=None, max_length=8)
    # "Remove the line instead": the conservative alternative to any claim
    # edit (an NCCI bundling edit reads "add a modifier if distinct — otherwise
    # remove the line", and only the doctor knows which).
    remove: bool = False
    # Unit changes only: rewrite the line charge as price-per-unit × new units
    # ("scale", how billing systems build 24F) or leave it ("keep", for a
    # units typo). Box 28 is recomputed either way.
    charge: Literal["scale", "keep"] = "scale"


class CorrectedClaimRequest(BaseModel):
    selections: list[CorrectedClaimSelection] = Field(min_length=1, max_length=20)


class CorrectedClaimEditResult(BaseModel):
    index: int
    kind: str
    target: str | None
    value: str | None
    applied: bool
    reason: str | None  # claim_patch skip reason code
    applied_lines: int = 0  # a code can sit on several service lines
    note: str | None = None  # advisory: check_dx_pointers, charge_not_scaled
    charge_before_cents: int | None = None  # scaled unit change: 24F before/after
    charge_after_cents: int | None = None


class CorrectedClaimDetail(BaseModel):
    id: UUID
    version: int
    results: list[CorrectedClaimEditResult]
    # None = no charge changed; False = a line was removed but the Box 28 total
    # could not be located, so the user must fix it by hand.
    total_updated: bool | None
    # False when nothing could be applied — there is no file to download.
    downloadable: bool
    # "form": the claim was a fillable PDF and the corrected copy stays fillable;
    # "text": born-digital page text edited in place.
    format: str | None = None
    created_at: datetime
    downloaded_at: datetime | None


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
    case_type: str = "appeal"
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
    # Pre-check cases only: the latest risk report. Always None for appeals.
    risk_report: RiskReportDetail | None = None
    # Pre-check cases only: whether the draft claim has a text layer the
    # patcher can edit (a scanned claim gets the edits-only view), and the
    # latest corrected version if one was made.
    claim_editable: bool = False
    corrected_claim: CorrectedClaimDetail | None = None


class CaseStatusResponse(BaseModel):
    id: UUID
    status: str


class CaseStatusPollResponse(BaseModel):
    # PHI-free shape for the detail page's processing poll (no audit needed).
    id: UUID
    status: str
    stalled: bool = False


class ProcessingItem(BaseModel):
    id: UUID
    case_type: str


class ProcessingIdsResponse(BaseModel):
    # PHI-free feed for the background "is anything done yet?" poll.
    # `ids` is the original shape and MUST stay — the deployed notifier reads
    # it, and dropping it during a deploy window would silently kill ready-
    # toasts. `items` is the additive, typed shape the notifier migrates to.
    ids: list[UUID]
    items: list[ProcessingItem] = []


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
    # Appeal cases only — pre-checks are counted separately so the recovery
    # stats keep meaning "appeals" (win rate over pre-checks is nonsense).
    month_case_count: int
    month_pre_check_count: int = 0
    resolved_count: int
    win_count: int
    win_rate: float | None
    total_recovered_cents: int
    pending_outcomes: list[PendingOutcomeItem]
