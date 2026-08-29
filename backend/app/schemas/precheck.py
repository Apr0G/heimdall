"""Structured outputs for the pre-check pipeline (extraction + risk review).

Same leniency philosophy as schemas/extraction.py: normalize the model's
routine quirks ("" for null, missing lists) instead of burning the one retry,
but fail loudly on unit errors (floats for money) and drop rather than trust
anything outside the known vocabulary (check ids, severities).
"""

import re
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
        stripped = value.strip().replace(",", "")
        if "$" in stripped:
            # A currency sign is a dollar figure by definition: "$450" must
            # not become 450 cents.
            raise ValueError(f"{field} must be an integer number of cents, not dollars")
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
        # A missing/None/0 units means "not stated" — bill-once is the safe read
        # (a blank units cell is as likely read as 0 as null). Falsy → 1 rather
        # than failing the whole extraction on one line.
        if not cleaned.get("units"):
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
        # See ExtractionResult: an unhashable value must degrade, not raise.
        return value if isinstance(value, str) and value in PLAN_TYPES else "unknown"


# Proposed-edit vocabulary. remove_line / add_modifier / change_units /
# change_code are claim edits a biller applies in the PM system; documentation
# is a task for the clinician (edit the note, not the claim).
EDIT_KINDS = ("remove_line", "add_modifier", "change_units", "change_code", "documentation")
MAX_EDITS = 10


def _clip(value: object, limit: int) -> str | None:
    """Truncate over-long model text instead of failing validation — burning
    the one retry on verbosity would be a worse outcome than a clipped line."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[: limit - 1] + "…" if len(text) > limit else text


class RiskFinding(BaseModel):
    """One flag. `source` is stamped server-side ('ncci' or 'model'), never
    taken from model output. Text fields are clipped, not rejected — the
    report leads with titles; prose is collapsed detail."""

    check_id: str
    severity: Literal["high", "medium", "low", "info"] = "low"
    title: str = Field(min_length=1)
    predicted_carc: str | None = Field(default=None, max_length=16)
    explanation: str | None = None
    suggested_fix: str | None = None
    source: str = "model"

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: object) -> str:
        # Unknown severity degrades to "low" rather than failing the run —
        # the finding text is still worth showing, just not worth escalating.
        normalized = str(value).strip().lower() if value is not None else ""
        return normalized if normalized in SEVERITIES else "low"

    @field_validator("title", mode="before")
    @classmethod
    def _clip_title(cls, value: object) -> object:
        return _clip(value, 120) or value

    @field_validator("predicted_carc", mode="before")
    @classmethod
    def _clip_carc(cls, value: object) -> str | None:
        # Clip an over-long code annotation ("CO-16 (missing information)")
        # rather than reject and fail the whole review parse.
        return _clip(value, 16)

    @field_validator("explanation", "suggested_fix", mode="before")
    @classmethod
    def _clip_prose(cls, value: object) -> str | None:
        return _clip(value, 500)


# The value an edit writes onto the claim, by kind. Anything else is dropped to
# None (the edit survives as prose; only the one-click apply loses it), and the
# same patterns gate client-chosen values server-side in services/claim_patch.py.
_EDIT_VALUE_RE = {
    "add_modifier": re.compile(r"^[A-Z0-9]{2}$"),
    "change_units": re.compile(r"^[1-9]\d{0,2}$"),
    # CPT/HCPCS, or an ICD-10-CM code for a Box 21 (diagnosis) correction —
    # the ICD-10 shape must match services/claim_patch._ICD10_RE (7th-character
    # extensions, X placeholders, a letter in position 3, the U chapter).
    "change_code": re.compile(
        r"^(?:\d{5}|\d{4}[FTU]|[A-Z]\d{4}|[A-Z]\d[A-Z0-9](?:\.?[A-Z0-9]{1,4})?)$"
    ),
}


def normalize_edit_value(kind: str, value: object) -> str | None:
    pattern = _EDIT_VALUE_RE.get(kind)
    if pattern is None or value is None:
        return None
    text = str(value).strip().upper()
    return text if pattern.match(text) else None


class ProposedEdit(BaseModel):
    """One concrete change, stated as a diff line — apply-in-the-PM brief.
    `source` is stamped server-side; the deterministic engine's edits merge
    ahead of the model's and can never be displaced by them."""

    kind: Literal["remove_line", "add_modifier", "change_units", "change_code", "documentation"]
    # The code/line the edit applies to (e.g. "20610"); None for note tasks.
    target: str | None = Field(default=None, max_length=16)
    instruction: str = Field(min_length=1)
    # The new modifier / unit count / code, so the edit can be applied to the
    # PDF without re-parsing the instruction. None = the biller decides.
    value: str | None = None
    source: str = "model"

    @field_validator("target", mode="before")
    @classmethod
    def _clip_target(cls, value: object) -> str | None:
        return _clip(value, 16)

    @model_validator(mode="after")
    def _normalize_value(self) -> "ProposedEdit":
        object.__setattr__(self, "value", normalize_edit_value(self.kind, self.value))
        return self

    @field_validator("instruction", mode="before")
    @classmethod
    def _clip_instruction(cls, value: object) -> object:
        return _clip(value, 160) or value


class RiskReviewResult(BaseModel):
    """Structured output of the documentation-review prompt. Findings with a
    check_id outside the model's fixed vocabulary — and edits with an unknown
    kind — are dropped (counted, never trusted); both lists are capped."""

    findings: list[RiskFinding] = []
    proposed_edits: list[ProposedEdit] = []
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
            # Drop (and count) anything outside the vocabulary OR missing a
            # usable title — a single degenerate finding must not fail the whole
            # parse (the contract is drop-not-reject).
            if (
                isinstance(item, dict)
                and item.get("check_id") in MODEL_CHECK_IDS
                and str(item.get("title") or "").strip()
            ):
                kept.append({**item, "source": "model"})
            else:
                dropped += 1
        raw_edits = data.get("proposed_edits") or []
        if not isinstance(raw_edits, list):
            raw_edits = []
        kept_edits: list = []
        for item in raw_edits:
            if (
                isinstance(item, dict)
                and item.get("kind") in EDIT_KINDS
                and str(item.get("instruction") or "").strip()
            ):
                kept_edits.append({**item, "source": "model"})
            else:
                dropped += 1
        # Prioritize by severity before the cap so a high-severity finding at
        # position 31 isn't discarded in favor of an info at position 3; count
        # what the cap truncates, per the "dropped, never trusted" contract.
        _order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        kept.sort(key=lambda f: _order.get(str(f.get("severity", "")).strip().lower(), 2))
        dropped += max(0, len(kept) - MAX_FINDINGS) + max(0, len(kept_edits) - MAX_EDITS)
        return {
            **data,
            "findings": kept[:MAX_FINDINGS],
            "proposed_edits": kept_edits[:MAX_EDITS],
            "dropped_count": dropped,
        }
