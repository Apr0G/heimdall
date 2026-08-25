from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.analysis import APPEAL_LEVELS

# A real appeal letter has a header block, a denial citation, a clinical narrative,
# a policy citation, an evidence list, an ask, and a signature. Nothing that short
# is a letter — it is a truncated or refused generation wearing a letter's shape.
MIN_BODY_CHARS = 400


class LetterDraft(BaseModel):
    """Structured output of the letter prompt. The canonical artifact is `body`
    (the full, copy-paste-ready letter including its own subject line). Lenient
    on the enum so a slightly-off appeal_type doesn't burn a retry — but NOT
    lenient on `body`, which is the entire product.

    `body` was previously `str = ""` with a None -> "" normalizer, so an omitted or
    null body VALIDATED. The permitted retry never fired, the model_run was never
    failed, and the case went `ready` with an empty letter behind an active
    Download button that 404s. Hard rule 9: no empty success states.
    """

    subject_line: str = ""
    body: str = Field(min_length=MIN_BODY_CHARS)
    appeal_type: str = "level_1_internal"
    attachments_referenced: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        cleaned: dict = {}
        for key, value in data.items():
            # `body` is deliberately excluded from the None -> "" coercion: turning a
            # missing body into an empty string is what made the failure silent.
            if value is None and key != "body":
                value = [] if key == "attachments_referenced" else ""
            # str() coercion applies to subject_line ONLY. A non-string `body`
            # (the model emitting a list of paragraphs or a dict) is a structural
            # parse failure — str()'ing it to a repr that clears MIN_BODY_CHARS
            # would ship "['…', '…']" as the letter. Let it fail and retry.
            if key == "subject_line" and value is not None and not isinstance(value, str):
                value = str(value)
            cleaned[key] = value
        return cleaned

    @field_validator("body", mode="after")
    @classmethod
    def _reject_whitespace_body(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("letter body is empty")
        return value

    @field_validator("appeal_type", mode="before")
    @classmethod
    def _normalize_appeal_type(cls, value: object) -> str:
        return value if value in APPEAL_LEVELS else "level_1_internal"

    @field_validator("attachments_referenced", mode="before")
    @classmethod
    def _coerce_attachments(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]
