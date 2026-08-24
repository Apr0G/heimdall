"""Structured outputs for the pre-check pipeline (extraction + risk review).

Same leniency philosophy as schemas/extraction.py: normalize the model's
routine quirks ("" for null, missing lists) instead of burning the one retry,
but fail loudly on unit errors (floats for money) and drop rather than trust
anything outside the known vocabulary (check ids, severities).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.extraction import PLAN_TYPES

# The fixed check vocabulary. The model may only report these; anything else is
# dropped at validation (never trusted into the report). The ncci_* / dos_* ids
# are reserved for the deterministic engine — the model must not emit them, so
# they are not in the model's allowed set.
MODEL_CHECK_IDS = frozenset(
    [
        "em_level_mdm",
        "em_time",
        "modifier_25",
        "modifier_59",
        "medical_necessity_narrative",
        "dx_specificity",
        "time_double_dipping",
        "laterality_units",
        "rx_substantiation",
    ]
)
DETERMINISTIC_CHECK_IDS = frozenset(["ncci_ptp", "ncci_mue", "ncci_unavailable", "dos_missing"])

SEVERITIES = ("high", "medium", "low", "info")

# Bound the report size — a runaway model must not produce an unrenderable
# 500-finding report (and the JSONB row stays small).
MAX_FINDINGS = 30

_LIST_FIELDS = {"modifiers", "icd10", "claim_lines", "icd10_codes"}


def _reject_money_float(value: object, *, field: str) -> object:
    """Hard rule 11: money is integer cents. A float always means the model
    answered in dollars — reject, don't round (same rationale as extraction)."""
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer number of cents")
    if isinstance(value, float):
        raise ValueError(f"{field} must be an integer number of cents, not a float")
    if isinstance(value, str):
        stripped = value.strip().replace(",", "").removeprefix("$")
        if "." in stripped:
            raise ValueError(f"{field} must be an integer number of cents, not a decimal")
        return stripped or None
    return value


class ClaimLine(BaseModel):
    """One billed line of the draft claim."""

    cpt: str = Field(min_length=1, max_length=8)
    modifiers: list[str] = []
    units: int = Field(default=1, ge=1, le=999)
    icd10: list[str] = []
    pos: str | None = None
    charge_cents: int | None = Field(default=None, ge=0)

    @field_validator("charge_cents", mode="before")
    @classmethod
    def _money(cls, value: object) -> object:
        return _reject_money_float(value, field="charge_cents")

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
        # A missing/None units means "not stated" — bill-once is the safe read.
        if cleaned.get("units") is None:
            cleaned["units"] = 1
        return cleaned


class PrecheckExtractionResult(BaseModel):
    """Structured output of the pre-check extraction prompt (draft claim +
    clinical notes — no denial document, so no CARC/denial fields)."""

    payer_name: str | None = None
    plan_type: str = "unknown"
    claim_number: str | None = None
    member_id: str | None = None  # raw — hashed before persistence, never stored
    patient_initials: str | None = Field(default=None, max_length=16)
    date_of_service: date | None = None
    billed_amount_cents: int | None = Field(default=None, ge=0)
    claim_lines: list[ClaimLine] = []
    # Claim-level diagnosis list (union of the line-level pointers).
    icd10_codes: list[str] = []
    clinical_summary: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("billed_amount_cents", mode="before")
    @classmethod
    def _money(cls, value: object) -> object:
        return _reject_money_float(value, field="billed_amount_cents")

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


class RiskFinding(BaseModel):
    """One flag. `source` is stamped server-side ('ncci' or 'model'), never
    taken from model output."""

    check_id: str
    severity: Literal["high", "medium", "low", "info"] = "low"
    title: str = Field(min_length=1, max_length=200)
    predicted_carc: str | None = Field(default=None, max_length=16)
    explanation: str | None = Field(default=None, max_length=2000)
    suggested_fix: str | None = Field(default=None, max_length=2000)
    source: str = "model"

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: object) -> str:
        # Unknown severity degrades to "low" rather than failing the run —
        # the finding text is still worth showing, just not worth escalating.
        normalized = str(value).strip().lower() if value is not None else ""
        return normalized if normalized in SEVERITIES else "low"


class RiskReviewResult(BaseModel):
    """Structured output of the documentation-review prompt. Findings with a
    check_id outside the model's fixed vocabulary are dropped (counted, never
    trusted), and the list is capped at MAX_FINDINGS."""

    findings: list[RiskFinding] = []
    dropped_count: int = 0  # populated by the validator, not the model

    @model_validator(mode="before")
    @classmethod
    def _filter_findings(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        raw = data.get("findings") or []
        if not isinstance(raw, list):
            raw = []
        kept: list = []
        dropped = 0
        for item in raw:
            if isinstance(item, dict) and item.get("check_id") in MODEL_CHECK_IDS:
                item = {**item, "source": "model"}
                kept.append(item)
            else:
                dropped += 1
        return {**data, "findings": kept[:MAX_FINDINGS], "dropped_count": dropped}
