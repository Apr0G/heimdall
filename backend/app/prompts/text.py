"""Shared handling for untrusted document text before it enters a prompt.

Every prompt in this package interpolates text that came out of a PDF a user
uploaded. Two things must happen to it first, and they were previously done
nowhere:

1. **Bound it.** Extracted text went from Textract into the prompt with no cap, so
   a long document produced three oversized Bedrock calls per case (extraction,
   analysis, letter). Past the context window Bedrock returns a ValidationException
   and the case errors *after* paying for the attempt; below it, one case can burn
   a six-figure input-token count three times over with no ceiling and no alert.

2. **Neutralise the section fences.** The prompts delimit untrusted input with
   `=== SECTION ===` markers and tell the model to treat anything between them as
   data. A PDF whose own text contains that pattern can close the fence early and
   have the rest of its content read as prompt. The threat model is same-tenant
   (the uploader only reaches their own case) and model output is fully enum-coerced
   downstream, which is why this was rated LOW — but it costs one regex to remove.
"""

import re

# Roughly 100k characters ~ 25k tokens per section. Three sections plus JSON stays
# comfortably inside the model's window while leaving room for the letter draft.
# Clinical notes get the larger budget because they carry the appeal's argument.
DEFAULT_MAX_CHARS = 100_000
CLINICAL_MAX_CHARS = 160_000

TRUNCATION_MARKER = "\n\n[... TRUNCATED: document exceeded the extraction limit ...]"

# A line consisting only of a === ... === fence, which is our section delimiter.
_FENCE_LINE = re.compile(r"^[ \t]*={2,}.*={2,}[ \t]*$", re.MULTILINE)


def strip_fences(text: str) -> str:
    """Defang any line that mimics our own `=== SECTION ===` delimiter."""
    return _FENCE_LINE.sub(lambda m: m.group(0).replace("=", "-"), text)


def prepare(text: str | None, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Fence-strip and length-bound one untrusted section for prompt inclusion.

    Truncation is marked in-band so the model — and anyone reading the archived
    request in `model_runs/` — can see the text was shortened. A silently
    shortened clinical narrative must never be mistaken for a complete one.
    """
    if not text:
        return ""
    cleaned = strip_fences(text.strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + TRUNCATION_MARKER


def prepare_json_text(value, *, max_chars: int = DEFAULT_MAX_CHARS):
    """Recursively run `prepare` over every string inside a dict/list that is
    about to be json.dumps'd into a prompt. Model-derived JSON (extraction,
    analysis) carries free text the model wrote FROM an untrusted document, so
    it gets the same fence-strip and length bound as raw document text."""
    if isinstance(value, str):
        return prepare(value, max_chars=max_chars)
    if isinstance(value, dict):
        return {k: prepare_json_text(v, max_chars=max_chars) for k, v in value.items()}
    if isinstance(value, list):
        return [prepare_json_text(v, max_chars=max_chars) for v in value]
    return value


def was_truncated(*sections: str) -> bool:
    """Whether any prepared section was shortened — recorded on the model_run."""
    return any(TRUNCATION_MARKER in section for section in sections)
