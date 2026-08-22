import pytest
from pydantic import ValidationError

from app.prompts import analysis_prompt
from app.schemas.analysis import AnalysisResult
from app.services.analysis import never_appealable_codes, probability_band


def test_prompt_version_is_pinned():
    assert analysis_prompt.VERSION == "analyze_v4"


def test_probability_band_thresholds():
    assert probability_band(0.10) == "low"
    assert probability_band(0.34) == "low"
    assert probability_band(0.35) == "moderate"
    assert probability_band(0.65) == "moderate"
    assert probability_band(0.66) == "high"
    assert probability_band(0.90) == "high"


def test_probability_band_is_none_when_not_estimated():
    """A band is derived from an estimate. With no estimate there is no band —
    returning "moderate" showed a confidence the model never produced."""
    assert probability_band(None) is None


@pytest.mark.parametrize("value", [95, 1.5, -0.1, 100])
def test_success_probability_out_of_range_is_rejected(value):
    """Numeric(4,3) overflows above 9.999, and the failing INSERT's bound
    parameters carry PHI into the traceback. Reject at the schema boundary."""
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate({"is_appealable": True, "success_probability": value})


@pytest.mark.parametrize(
    "codes",
    [
        ["CO-45"],
        ["PR-1"],
        ["PR-204"],
        ["co-45"],
        ["CO-50", "PR-2"],
        ["CO 45"],
        ["CO45"],
        ["CO_45"],
        ["PR1"],
    ],
)
def test_never_appealable_codes_detected(codes):
    """Every spelling the extraction model might emit. A guard that recognises
    only the hyphenated form fails open — it is the control, not the prompt."""
    assert never_appealable_codes(codes)


def test_never_appealable_codes_are_canonical():
    assert never_appealable_codes(["co 45", "CO45"]) == ["CO-45"]


def test_bare_reason_code_uses_group_codes():
    # Extraction may split "CO-45" into carc_codes=["45"], group_codes=["CO"].
    assert never_appealable_codes(["45"], ["CO"]) == ["CO-45"]
    assert never_appealable_codes(["1"], ["PR", "CO"]) == ["PR-1"]
    assert never_appealable_codes(["45"]) == []  # no group: can't decide, don't guess
    assert never_appealable_codes(["N/A", "", "CO-450"]) == []


@pytest.mark.parametrize("codes", [[], None, ["CO-50"], ["CO-97"], ["CO-151"], ["CO-16"]])
def test_appealable_codes_pass_the_guard(codes):
    """CO-97 is explicitly NOT in the never-appeal set: the NCCI PTP modifier
    indicator that decides it is absent from every document we receive."""
    assert never_appealable_codes(codes) == []


def test_unknown_category_and_level_normalized():
    result = AnalysisResult.model_validate(
        {"denial_category": "weird", "recommended_appeal_level": "made_up"}
    )
    assert result.denial_category == "other"
    assert result.recommended_appeal_level == "level_1_internal"


def test_is_appealable_and_empties_coerced():
    result = AnalysisResult.model_validate(
        {
            "is_appealable": "",
            "appealability_reason": "",
            "additional_documents_needed": "",
        }
    )
    assert result.is_appealable is False
    assert result.appealability_reason is None
    assert result.additional_documents_needed == []


def test_additional_documents_filtered_to_valid():
    """ "imaging" is filtered out alongside "garbage": no doc_type enum member and no
    upload endpoint accepts it, so requesting it silently discards the ask."""
    result = AnalysisResult.model_validate(
        {"additional_documents_needed": ["prior_auth", "garbage", "imaging"]}
    )
    assert result.additional_documents_needed == ["prior_auth"]


def test_new_never_appeal_categories_accepted():
    for category in ("contractual_adjustment", "patient_responsibility"):
        result = AnalysisResult.model_validate({"denial_category": category})
        assert result.denial_category == category


def test_well_formed_analysis_parses():
    result = AnalysisResult.model_validate(
        {
            "denial_category": "medical_necessity",
            "is_appealable": True,
            "appealability_reason": "CO-50 is appealable with clinical support.",
            "success_probability": 0.55,
            "probability_band": "moderate",
            "reasoning_text": "Strong notes. This is an AI-generated estimate ...",
            "recommended_appeal_level": "level_1_internal",
            "additional_documents_needed": [],
        }
    )
    assert result.is_appealable is True
    assert result.success_probability == 0.55
    assert probability_band(result.success_probability) == "moderate"
