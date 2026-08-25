import pytest
from pydantic import ValidationError

from app.models import Analysis
from app.prompts import letter_prompt
from app.schemas.letter import MIN_BODY_CHARS, LetterDraft
from app.services.letter import (
    format_amount_cents,
    next_letter_version,
    should_draft_letter,
)

# A body long enough to clear MIN_BODY_CHARS, so tests about OTHER fields aren't
# accidentally testing the length rule.
_VALID_BODY = (
    "To Whom It May Concern:\n\n"
    "We are appealing the denial of claim CLM-TEST-0001 for patient J.D., "
    "date of service 2026-05-01. The claim was denied citing CARC CO-50. "
    "The clinical record documents six weeks of conservative therapy without "
    "improvement, which satisfies the criteria in your own medical policy for "
    "advanced imaging. We have enclosed the denial letter, the original "
    "CMS-1500, and the complete clinical notes. We request that you reverse "
    "this denial and remit payment of $450.00.\n\nSincerely,\n"
)


def _draft(**overrides) -> dict:
    return {"body": _VALID_BODY, **overrides}


def test_prompt_version_is_pinned():
    assert letter_prompt.VERSION == "letter_v6"


def test_unknown_appeal_type_normalized():
    assert (
        LetterDraft.model_validate(_draft(appeal_type="made_up")).appeal_type == "level_1_internal"
    )
    assert (
        LetterDraft.model_validate(_draft(appeal_type="peer_to_peer")).appeal_type == "peer_to_peer"
    )


def test_nulls_coerced_except_body():
    result = LetterDraft.model_validate(_draft(subject_line=None, attachments_referenced=None))
    assert result.subject_line == ""
    assert result.attachments_referenced == []


# --- HIGH-04: an empty body must FAIL, not validate ---------------------------
#
# `body: str = ""` plus a None -> "" normalizer meant {}, {"body": None},
# {"body": ""} and {"body": "   "} all validated. The permitted retry never fired,
# the model_run was never failed, and the case went `ready` with an empty letter
# behind an active Download button that 404s. Hard rule 9: no empty success states.


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"body": None},
        {"body": ""},
        {"body": "   "},
        {"body": "\n\t "},
        {"body": "Too short to be a letter."},
    ],
    ids=["missing", "null", "empty", "spaces", "whitespace", "too-short"],
)
def test_empty_or_stub_body_is_rejected(payload):
    with pytest.raises(ValidationError):
        LetterDraft.model_validate(payload)


def test_minimum_body_length_is_enforced_at_the_boundary():
    with pytest.raises(ValidationError):
        LetterDraft.model_validate({"body": "x" * (MIN_BODY_CHARS - 1)})
    assert LetterDraft.model_validate({"body": "x" * MIN_BODY_CHARS}).body


def test_attachments_filtered_of_empties():
    result = LetterDraft.model_validate(
        _draft(attachments_referenced=["denial letter", "", "clinical notes"])
    )
    assert result.attachments_referenced == ["denial letter", "clinical notes"]


def test_well_formed_letter_parses():
    result = LetterDraft.model_validate(
        _draft(
            subject_line="Re: Appeal of Denied Claim #CLM-TEST-0001 for J.D., DOS 2026-05-01",
            appeal_type="level_1_internal",
            attachments_referenced=["denial letter", "original claim (CMS-1500)"],
        )
    )
    assert result.body.startswith("To Whom")
    assert result.appeal_type == "level_1_internal"


def test_should_draft_letter_only_for_appealable():
    assert should_draft_letter(None) is False
    assert should_draft_letter(Analysis(is_appealable=False)) is False
    assert should_draft_letter(Analysis(is_appealable=True)) is True


def test_next_letter_version_increments():
    assert next_letter_version([]) == 1
    assert next_letter_version([1]) == 2
    assert next_letter_version([1, 2, 3]) == 4


def test_format_amount_cents():
    assert format_amount_cents(45000) == "$450.00"
    assert format_amount_cents(120000) == "$1,200.00"
    assert format_amount_cents(None) == "the denied amount"


def test_format_amount_cents_uses_integer_arithmetic():
    """Hard rule 11 — no float division on currency, including sub-dollar and
    exact-dollar boundaries where a float would be most likely to drift."""
    assert format_amount_cents(0) == "$0.00"
    assert format_amount_cents(5) == "$0.05"
    assert format_amount_cents(99) == "$0.99"
    assert format_amount_cents(100) == "$1.00"
    assert format_amount_cents(100_000_000_00) == "$100,000,000.00"


# --- LOW-17: the letter must be written as the recommended appeal level -------


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("level_1_internal", "first-level internal appeal"),
        ("peer_to_peer", "peer-to-peer"),
        ("level_2_internal", "second-level internal appeal"),
        ("external_review", "external / independent review"),
    ],
)
def test_appeal_level_reaches_the_prompt(level, expected):
    prompt = letter_prompt.build_user_prompt({}, {}, {}, "notes", appeal_level=level)
    assert expected in prompt


def test_unknown_appeal_level_falls_back_to_first_level():
    prompt = letter_prompt.build_user_prompt({}, {}, {}, "notes", appeal_level="nonsense")
    assert "first-level internal appeal" in prompt
