from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

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
    # Bounded: this is interpolated into a Content-Disposition filename, which
    # Starlette encodes as latin-1. Long or exotic values are rejected here rather
    # than 500ing the letter download with no UI path to fix the stored value.
    patient_initials: str | None = Field(default=None, max_length=16)
    date_of_service: date | None = None
    denial_date: date | None = None
    billed_amount_cents: int | None = Field(default=None, ge=0)
    denied_amount_cents: int | None = Field(default=None, ge=0)
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
    # Bounded because the DB column is Numeric(3,2) — max 9.99. The model returning
    # 95 for "95% confident" instead of 0.95 is a routine failure mode, and the
    # resulting overflow puts the failing INSERT's bound parameters (claim number,
    # payer, extracted JSON) into a traceback that reaches CloudWatch.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("billed_amount_cents", "denied_amount_cents", mode="before")
    @classmethod
    def _reject_dollar_valued_floats(cls, value: object) -> object:
        """Reject ANY float, not just a non-integral one. Pydantic lax mode
        truncates 450.0 -> 450 silently, so a model that answered in DOLLARS
        records a $450 claim as $4.50 — a 100x error that flows into the letter
        prompt's "denied amount" and into total_recovered_cents. 450.5 already
        failed loudly; the whole-dollar case was the silent, dangerous half.

        A float here always means the model misunderstood the unit, because cents
        are integral by definition. Failing consumes the one permitted retry and
        then fails the model_run, which is the correct loud outcome under hard
        rule 9 — far better than a wrong dollar figure in a mailed appeal.

        Hard rule 11: money is integer cents, never a float.
        """
        if isinstance(value, bool):
            raise ValueError("amount must be an integer number of cents")
        if isinstance(value, float):
            raise ValueError(
                "amount must be an integer number of cents, not a float "
                "(a decimal here usually means dollars were returned instead)"
            )
        if isinstance(value, str):
            stripped = value.strip().replace(",", "").removeprefix("$")
            if "." in stripped:
                raise ValueError("amount must be an integer number of cents, not a decimal")
            return stripped or None
        return value

    @model_validator(mode="after")
    def _denied_cannot_exceed_billed(self) -> "ExtractionResult":
        """A payer cannot deny more than was billed. When it happens the model has
        misread one of the two figures, and both flow into the letter prompt's
        "denied amount" and into total_recovered_cents."""
        if (
            self.billed_amount_cents is not None
            and self.denied_amount_cents is not None
            and self.denied_amount_cents > self.billed_amount_cents
        ):
            raise ValueError("denied_amount_cents cannot exceed billed_amount_cents")
        return self

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
