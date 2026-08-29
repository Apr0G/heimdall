from pydantic import BaseModel, Field, field_validator

from app.schemas.analysis import APPEAL_LEVELS

# A real appeal letter has a header block, a denial citation, a clinical narrative,
# a policy citation, an evidence list, an ask, and a signature. Nothing that short
# is a letter — it is a truncated or refused generation wearing a letter's shape.
MIN_BODY_CHARS = 400


class LetterDraft(BaseModel):
    """Structured output of the letter prompt. The canonical artifact is `body`
    (the full, copy-paste-ready letter including its own subject line and
    enclosure list — nothing else the model returns is stored or rendered, so
    nothing else is asked for). Lenient on the enum so a slightly-off
    appeal_type doesn't burn a retry — but NOT lenient on `body`, which is the
    entire product.

    `body` was previously `str = ""` with a None -> "" normalizer, so an omitted or
    null body VALIDATED. The permitted retry never fired, the model_run was never
    failed, and the case went `ready` with an empty letter behind an active
    Download button that 404s. Hard rule 9: no empty success states.
    """

    # No coercion on `body`: a None or non-string body (the model emitting a list
    # of paragraphs or a dict) is a structural parse failure — str()'ing it to a
    # repr that clears MIN_BODY_CHARS would ship "['…', '…']" as the letter. Let
    # it fail and retry.
    body: str = Field(min_length=MIN_BODY_CHARS)
    appeal_type: str = "level_1_internal"

    @field_validator("body", mode="after")
    @classmethod
    def _reject_whitespace_body(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("letter body is empty")
        return value

    @field_validator("appeal_type", mode="before")
    @classmethod
    def _normalize_appeal_type(cls, value: object) -> str:
        # An unhashable value (list/dict) or None must degrade, not raise.
        return value if isinstance(value, str) and value in APPEAL_LEVELS else "level_1_internal"
