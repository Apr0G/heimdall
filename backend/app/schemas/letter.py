from pydantic import BaseModel, field_validator, model_validator

from app.schemas.analysis import APPEAL_LEVELS


class LetterDraft(BaseModel):
    """Structured output of the letter prompt. The canonical artifact is `body`
    (the full, copy-paste-ready letter including its own subject line). Lenient
    on the enum so a slightly-off appeal_type doesn't burn a retry."""

    subject_line: str = ""
    body: str = ""
    appeal_type: str = "level_1_internal"
    attachments_referenced: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        cleaned: dict = {}
        for key, value in data.items():
            if value is None:
                value = [] if key == "attachments_referenced" else ""
            if key in {"subject_line", "body"} and not isinstance(value, str):
                value = str(value)
            cleaned[key] = value
        return cleaned

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
