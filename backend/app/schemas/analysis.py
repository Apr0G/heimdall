from pydantic import BaseModel, Field, field_validator, model_validator

DENIAL_CATEGORIES = {
    "medical_necessity",
    "prior_auth",
    "coding_error",
    "bundling",
    "timely_filing",
    "non_covered",
    "missing_info",
    "wrong_payer",
    "contractual_adjustment",
    "patient_responsibility",
    "other",
}

APPEAL_LEVELS = {
    "level_1_internal",
    "peer_to_peer",
    "level_2_internal",
    "external_review",
}

# Must stay a subset of the doc_type enum AND of what the upload endpoint accepts:
# a request for a document type the doctor cannot upload is silently discarded,
# which loses a clinically meaningful ask. "imaging" was previously listed here and
# was exactly that dead end.
DOC_NEEDS = {"prior_auth", "prior_treatment", "none"}


class AnalysisResult(BaseModel):
    """Structured output of the analysis prompt. Lenient on enums (coerce to a
    safe default rather than fail) so a slightly-off label doesn't burn a retry.
    probability_band is re-derived server-side from success_probability."""

    denial_category: str = "other"
    # REQUIRED, no default. This is the most consequential field in the product:
    # a missing/null verdict must fail validation (consume the one retry, then
    # fail the model_run) rather than silently coerce to "not appealable", which
    # would send the case to `ready` with no letter and no error — an empty
    # success state (rule 9) that quietly writes off a winnable appeal. The
    # server-side never-appeal guard can only flip true→false, never rescue a
    # coerced false.
    is_appealable: bool
    appealability_reason: str | None = None
    # Bounded because the DB column is Numeric(4,3) — max 9.999. An unbounded value
    # (the model returning 95 instead of 0.95) overflows on flush, and the failing
    # INSERT's bound parameters carry PHI into the traceback.
    success_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    probability_band: str | None = None
    reasoning_text: str | None = None
    recommended_appeal_level: str = "level_1_internal"
    additional_documents_needed: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        cleaned: dict = {}
        for key, value in data.items():
            if value == "":
                value = [] if key == "additional_documents_needed" else None
            if key == "additional_documents_needed" and value is None:
                value = []
            # NB: is_appealable is deliberately NOT coerced from None → False —
            # a null/missing verdict must fail validation (see the field docstring).
            cleaned[key] = value
        return cleaned

    @field_validator("denial_category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> str:
        # `in` on a set raises TypeError for an unhashable value (a list or
        # dict from the model), which Pydantic does not wrap — guard the type.
        return value if isinstance(value, str) and value in DENIAL_CATEGORIES else "other"

    @field_validator("recommended_appeal_level", mode="before")
    @classmethod
    def _normalize_level(cls, value: object) -> str:
        return value if isinstance(value, str) and value in APPEAL_LEVELS else "level_1_internal"

    @field_validator("additional_documents_needed", mode="before")
    @classmethod
    def _filter_docs(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str) and item in DOC_NEEDS]
