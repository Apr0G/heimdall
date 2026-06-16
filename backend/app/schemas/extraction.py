from datetime import date

from pydantic import BaseModel, field_validator, model_validator

PLAN_TYPES = {
    "commercial",
    "medicare",
    "medicare_advantage",
    "medicaid",
    "medicaid_mco",
    "tricare",
    "other",
    "unknown",
}

_LIST_FIELDS = {
    "carc_codes",
    "rarc_codes",
    "group_codes",
    "cpt_codes",
    "icd10_codes",
    "modifiers",
    "pos_codes",
}


class ExtractionResult(BaseModel):
    """Structured output of the extraction prompt. Lenient on purpose: the model
    sometimes emits "" for unknown scalars or null for empty lists, so we
    normalize before validation rather than failing (and triggering a retry)."""

    payer_name: str | None = None
    plan_type: str = "unknown"
    claim_number: str | None = None
    member_id: str | None = None  # raw — hashed before persistence, never stored
    patient_initials: str | None = None
    date_of_service: date | None = None
    denial_date: date | None = None
    billed_amount_cents: int | None = None
    denied_amount_cents: int | None = None
    carc_codes: list[str] = []
    rarc_codes: list[str] = []
    group_codes: list[str] = []
    cpt_codes: list[str] = []
    icd10_codes: list[str] = []
    modifiers: list[str] = []
    pos_codes: list[str] = []
    provider_name: str | None = None
    provider_npi: str | None = None
    prior_auth_number: str | None = None
    clinical_summary: str | None = None
    confidence: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        cleaned: dict = {}
        for key, value in data.items():
            if value == "":
                value = [] if key in _LIST_FIELDS else None
            if key in _LIST_FIELDS and value is None:
                value = []
            cleaned[key] = value
        return cleaned

    @field_validator("plan_type", mode="before")
    @classmethod
    def _normalize_plan_type(cls, value: object) -> str:
        return value if value in PLAN_TYPES else "unknown"
