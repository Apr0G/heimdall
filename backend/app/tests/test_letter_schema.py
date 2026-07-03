from app.models import Analysis
from app.prompts import letter_prompt
from app.schemas.letter import LetterDraft
from app.services.letter import (
    format_amount_cents,
    next_letter_version,
    should_draft_letter,
)


def test_prompt_version_is_pinned():
    assert letter_prompt.VERSION == "letter_v3"


def test_unknown_appeal_type_normalized():
    assert LetterDraft.model_validate({"appeal_type": "made_up"}).appeal_type == "level_1_internal"
    assert LetterDraft.model_validate({"appeal_type": "peer_to_peer"}).appeal_type == "peer_to_peer"


def test_nulls_and_attachments_coerced():
    result = LetterDraft.model_validate(
        {"subject_line": None, "body": None, "attachments_referenced": None}
    )
    assert result.subject_line == ""
    assert result.body == ""
    assert result.attachments_referenced == []


def test_attachments_filtered_of_empties():
    result = LetterDraft.model_validate(
        {"attachments_referenced": ["denial letter", "", "clinical notes"]}
    )
    assert result.attachments_referenced == ["denial letter", "clinical notes"]


def test_well_formed_letter_parses():
    result = LetterDraft.model_validate(
        {
            "subject_line": "Re: Appeal of Denied Claim #CLM-TEST-0001 for J.D., DOS 2026-05-01",
            "body": "To Whom It May Concern: ...",
            "appeal_type": "level_1_internal",
            "attachments_referenced": ["denial letter", "original claim (CMS-1500)"],
        }
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
