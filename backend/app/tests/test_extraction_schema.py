from datetime import date

import pytest

from app.prompts import extraction_prompt
from app.schemas.extraction import ExtractionResult
from app.services.claude_client import _extract_json


def test_prompt_version_is_pinned():
    # Guards against silently changing the prompt without bumping the version.
    assert extraction_prompt.VERSION == "extract_v2"


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
    # raw member_id is excluded from the persisted JSON
    assert "member_id" not in result.model_dump(exclude={"member_id"})
