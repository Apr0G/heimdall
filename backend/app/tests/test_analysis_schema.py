from app.prompts import analysis_prompt
from app.schemas.analysis import AnalysisResult
from app.services.analysis import probability_band


def test_prompt_version_is_pinned():
    assert analysis_prompt.VERSION == "analyze_v2"


def test_probability_band_thresholds():
    assert probability_band(0.10) == "low"
    assert probability_band(0.34) == "low"
    assert probability_band(0.35) == "moderate"
    assert probability_band(0.65) == "moderate"
    assert probability_band(0.66) == "high"
    assert probability_band(0.90) == "high"
    assert probability_band(None) == "moderate"


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
    result = AnalysisResult.model_validate(
        {"additional_documents_needed": ["prior_auth", "garbage", "imaging"]}
    )
    assert result.additional_documents_needed == ["prior_auth", "imaging"]


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
