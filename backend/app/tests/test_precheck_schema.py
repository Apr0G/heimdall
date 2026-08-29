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

# (ProposedEdit is exercised through RiskReviewResult below.)


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

    def test_units_zero_or_missing_normalizes_to_one(self):
        # A blank/0 units cell means "not stated" — bill-once, don't fail the
        # whole extraction on one line.
        assert ClaimLine.model_validate({"cpt": "99213", "units": 0}).units == 1
        assert ClaimLine.model_validate({"cpt": "99213"}).units == 1

    def test_units_upper_bound(self):
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

    def test_overlong_text_clipped_not_rejected(self):
        result = RiskReviewResult.model_validate(
            {"findings": [_finding(explanation="x" * 3000, title="t" * 500)]}
        )
        assert len(result.findings[0].explanation) == 500
        assert result.findings[0].explanation.endswith("…")
        assert len(result.findings[0].title) == 120


def _edit(kind: str = "change_code", **overrides) -> dict:
    base = {"kind": kind, "target": "99214", "instruction": "Change 99214 to 99213"}
    base.update(overrides)
    return base


class TestProposedEditsFilter:
    def test_unknown_kinds_dropped_and_source_forced(self):
        result = RiskReviewResult.model_validate(
            {
                "findings": [],
                "proposed_edits": [
                    _edit(),
                    _edit("auto_apply"),  # not a real kind — dropped
                    _edit("documentation", target=None, source="ncci"),  # spoofed source
                ],
            }
        )
        assert [e.kind for e in result.proposed_edits] == ["change_code", "documentation"]
        assert all(e.source == "model" for e in result.proposed_edits)
        assert result.dropped_count == 1

    def test_cap_and_instruction_clip(self):
        result = RiskReviewResult.model_validate(
            {"findings": [], "proposed_edits": [_edit(instruction="y" * 999)] * 30}
        )
        assert len(result.proposed_edits) == 10
        assert len(result.proposed_edits[0].instruction) == 160

    def test_value_is_normalised_per_kind_or_dropped(self):
        result = RiskReviewResult.model_validate(
            {
                "findings": [],
                "proposed_edits": [
                    _edit("add_modifier", value=" xs "),
                    _edit("change_units", value="2"),
                    _edit("change_units", value="0"),  # units start at 1
                    _edit("change_code", value="99213"),
                    _edit("change_code", value="99213; DROP"),
                    _edit("change_code", value="n20.1"),  # ICD-10 for a Box 21 fix
                    _edit("remove_line", value="99213"),  # no value for a removal
                    _edit("documentation", value="anything"),
                ],
            }
        )
        assert [e.value for e in result.proposed_edits] == [
            "XS",
            "2",
            None,
            "99213",
            None,
            "N20.1",
            None,
            None,
        ]

    def test_non_list_tolerated(self):
        assert (
            RiskReviewResult.model_validate({"findings": [], "proposed_edits": "no"}).proposed_edits
            == []
        )


@pytest.mark.parametrize("value", [["medicare"], {"type": "medicare"}, 7])
def test_unhashable_plan_type_degrades_to_unknown(value):
    assert PrecheckExtractionResult.model_validate({"plan_type": value}).plan_type == "unknown"
