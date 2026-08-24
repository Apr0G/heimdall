"""Pre-check schema behaviors: money strictness, lenient normalization, and the
finding filter that keeps model output inside its vocabulary."""

import pytest
from pydantic import ValidationError

from app.schemas.precheck import (
    MAX_FINDINGS,
    ClaimLine,
    PrecheckExtractionResult,
    RiskReviewResult,
)


def _finding(check_id: str = "em_level_mdm", **overrides) -> dict:
    base = {
        "check_id": check_id,
        "severity": "high",
        "title": "Documentation does not support 99214",
        "predicted_carc": "CO-150",
        "explanation": "x",
        "suggested_fix": "y",
    }
    base.update(overrides)
    return base


class TestClaimLine:
    def test_defaults_and_normalization(self):
        line = ClaimLine.model_validate({"cpt": "99213", "modifiers": None, "units": None})
        assert line.units == 1 and line.modifiers == []

    def test_money_floats_rejected(self):
        with pytest.raises(ValidationError):
            ClaimLine.model_validate({"cpt": "99213", "charge_cents": 450.0})
        with pytest.raises(ValidationError):
            ClaimLine.model_validate({"cpt": "99213", "charge_cents": "45.00"})

    def test_unit_bounds(self):
        with pytest.raises(ValidationError):
            ClaimLine.model_validate({"cpt": "99213", "units": 0})
        with pytest.raises(ValidationError):
            ClaimLine.model_validate({"cpt": "99213", "units": 1000})


class TestPrecheckExtraction:
    def test_lenient_empties(self):
        result = PrecheckExtractionResult.model_validate(
            {"payer_name": "", "claim_lines": None, "icd10_codes": None, "plan_type": "bogus"}
        )
        assert result.payer_name is None
        assert result.claim_lines == [] and result.icd10_codes == []
        assert result.plan_type == "unknown"

    def test_total_money_rejects_float(self):
        with pytest.raises(ValidationError):
            PrecheckExtractionResult.model_validate({"billed_amount_cents": 450.0})


class TestRiskReviewFilter:
    def test_unknown_check_ids_dropped_and_counted(self):
        result = RiskReviewResult.model_validate(
            {
                "findings": [
                    _finding(),
                    _finding("made_up_check"),
                    # The deterministic ids are reserved — a model claiming them
                    # is dropped, so it can never spoof an "NCCI" finding.
                    _finding("ncci_ptp"),
                ]
            }
        )
        assert [f.check_id for f in result.findings] == ["em_level_mdm"]
        assert result.dropped_count == 2

    def test_source_forced_to_model(self):
        result = RiskReviewResult.model_validate({"findings": [_finding(source="ncci")]})
        assert result.findings[0].source == "model"

    def test_unknown_severity_degrades_to_low(self):
        result = RiskReviewResult.model_validate({"findings": [_finding(severity="CRITICAL!!")]})
        assert result.findings[0].severity == "low"

    def test_cap(self):
        result = RiskReviewResult.model_validate(
            {"findings": [_finding() for _ in range(MAX_FINDINGS + 20)]}
        )
        assert len(result.findings) == MAX_FINDINGS

    def test_non_list_findings_tolerated(self):
        assert RiskReviewResult.model_validate({"findings": "none"}).findings == []
