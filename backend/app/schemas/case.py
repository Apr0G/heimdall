from datetime import date
from uuid import UUID

from pydantic import BaseModel


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
