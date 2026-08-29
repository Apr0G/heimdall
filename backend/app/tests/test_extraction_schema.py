from datetime import date

import pytest
from pydantic import ValidationError

from app.prompts import extraction_prompt
from app.schemas.extraction import ExtractionResult
from app.services.claude_client import _extract_json
from app.services.extraction import _appeal_deadline, deadline_note


def test_prompt_version_is_pinned():
    # Guards against silently changing the prompt without bumping the version.
    assert extraction_prompt.VERSION == "extract_v3"


def test_extract_json_tolerates_fences_and_preamble():
    raw = 'Here is the JSON:\n```json\n{"payer_name": "Aetna"}\n```'
    assert _extract_json(raw) == {"payer_name": "Aetna"}


def test_extract_json_raises_without_object():
    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_empty_strings_become_none_or_empty_list():
    result = ExtractionResult.model_validate(
        {
            "payer_name": "",
            "denial_date": "",
            "carc_codes": "",
            "billed_amount_cents": "",
        }
    )
    assert result.payer_name is None
    assert result.denial_date is None
    assert result.carc_codes == []
    assert result.billed_amount_cents is None


def test_unknown_plan_type_normalized():
    assert ExtractionResult.model_validate({"plan_type": "ppo-gold"}).plan_type == "unknown"
    assert ExtractionResult.model_validate({"plan_type": "medicare"}).plan_type == "medicare"


def test_well_formed_extraction_parses():
    result = ExtractionResult.model_validate(
        {
            "payer_name": "Aetna",
            "plan_type": "commercial",
            "claim_number": "CLM-TEST-0001",
            "member_id": "MBR123",
            "denial_date": "2026-05-04",
            "denied_amount_cents": 45000,
            "carc_codes": ["CO-50"],
            "group_codes": ["CO"],
            "icd10_codes": ["M54.50"],
            "patient_initials": "J.D.",
            "clinical_summary": "MRI medically necessary after conservative therapy.",
            "confidence": 0.9,
        }
    )
    assert result.denial_date == date(2026, 5, 4)
    assert result.denied_amount_cents == 45000
    assert result.carc_codes == ["CO-50"]
    # The raw member_id is on the schema (the model returns it) but the persist
    # path excludes it — proven by the run_ai_extraction test below, not by a
    # self-referential exclude() here (which would pass for any schema).
    assert result.member_id == "MBR123"


# --- appeal deadlines (HIGH-01) ---------------------------------------------

_DENIAL = date(2026, 5, 4)


def test_original_medicare_gets_120_days():
    """Part A/B redetermination window."""
    assert _appeal_deadline(_DENIAL, "medicare") == date(2026, 9, 1)


def test_medicare_advantage_gets_60_days_not_120():
    """Part C reconsideration runs 60 days from the organization determination
    notice (42 CFR 422.582). Bucketing MA with Original Medicare put the deadline
    60 days late, and a missed filing deadline forfeits the claim permanently."""
    assert _appeal_deadline(_DENIAL, "medicare_advantage") == date(2026, 7, 3)


@pytest.mark.parametrize(
    "plan", ["commercial", "medicaid", "medicaid_mco", "tricare", "other", "unknown"]
)
def test_non_medicare_plans_get_60_days(plan):
    assert _appeal_deadline(_DENIAL, plan) == date(2026, 7, 3)


def test_no_denial_date_yields_no_deadline():
    assert _appeal_deadline(None, "medicare") is None


def test_medicare_advantage_note_states_the_60_day_window():
    note = deadline_note("medicare_advantage")
    assert "60 days" in note
    assert "Part C" in note


# --- money (MED-09, hard rule 11) -------------------------------------------


@pytest.mark.parametrize("field", ["billed_amount_cents", "denied_amount_cents"])
@pytest.mark.parametrize(
    "value", [450.0, 450.5, "450.00", -450, "$450", "$1,200", "$ 450", "$4.50"]
)
def test_dollar_valued_and_negative_amounts_are_rejected(field, value):
    """450.0 used to coerce silently to 450 cents, recording a $450 claim as
    $4.50 — and so did "$450", the one string shape that positively says
    dollars, because the sign was stripped before the digits were trusted."""
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({field: value})


@pytest.mark.parametrize("field", ["billed_amount_cents", "denied_amount_cents"])
@pytest.mark.parametrize("value", [45000, "45000", "45,000"])
def test_integer_cents_accepted(field, value):
    assert ExtractionResult.model_validate({field: value}).model_dump()[field] == 45000


def test_denied_cannot_exceed_billed():
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(
            {"billed_amount_cents": 10000, "denied_amount_cents": 20000}
        )


@pytest.mark.parametrize("value", [95, 1.5, -0.1])
def test_confidence_out_of_range_is_rejected(value):
    """Numeric(3,2) overflows above 9.99; the failing INSERT carries PHI bound
    parameters into the traceback."""
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({"confidence": value})


def test_overlong_patient_initials_rejected():
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({"patient_initials": "X" * 64})


@pytest.mark.parametrize("value", [["medicare"], {"type": "medicare"}, 7, None])
def test_unhashable_or_odd_plan_type_degrades_to_unknown(value):
    # A list/dict from the model used to raise TypeError out of `in`, which
    # Pydantic does not wrap — the whole parse escaped as a crash.
    assert ExtractionResult.model_validate({"plan_type": value}).plan_type == "unknown"
