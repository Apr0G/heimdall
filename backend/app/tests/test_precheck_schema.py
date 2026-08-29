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

    @pytest.mark.parametrize("value", [450.0, "45.00", "$450", "$1,200"])
    def test_money_floats_and_dollar_strings_rejected(self, value):
        with pytest.raises(ValidationError):
            ClaimLine.model_validate({"cpt": "99213", "charge_cents": value})

    def test_cents_strings_accepted(self):
        assert (
            ClaimLine.model_validate({"cpt": "99213", "charge_cents": "4,500"}).charge_cents == 4500
        )

    def test_units_zero_or_missing_normalizes_to_one(self):
        # A blank/0 units cell means "not stated" — bill-once, don't fail the
        # whole extraction on one line.
        assert ClaimLine.model_validate({"cpt": "99213", "units": 0}).units == 1
        assert ClaimLine.model_validate({"cpt": "99213"}).units == 1

    def test_numeric_codes_are_stringified(self):
        # "pos": 11 and "modifiers": [25, 59] are how a model often writes
        # two-digit codes; they used to fail the whole extraction.
        line = ClaimLine.model_validate(
            {"cpt": "99213", "pos": 11, "modifiers": [25, "59"], "icd10": ["N18.5"]}
        )
        assert (line.pos, line.modifiers, line.icd10) == ("11", ["25", "59"], ["N18.5"])
        # Booleans are not codes.
        with pytest.raises(ValidationError):
            ClaimLine.model_validate({"cpt": "99213", "modifiers": [True]})

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

    def test_blank_claim_lines_are_dropped_not_fatal(self):
        # An empty Box 24 row echoed as {"cpt": ""} (or null) used to fail the
        # whole extraction on ClaimLine's required code.
        result = PrecheckExtractionResult.model_validate(
            {
                "claim_lines": [
                    {"cpt": "99213", "units": 1},
                    {"cpt": "", "units": 1},
                    {"cpt": None},
                    {"cpt": "  "},
                    {"cpt": "20610", "units": 2},
                ]
            }
        )
        assert [(ln.cpt, ln.units) for ln in result.claim_lines] == [("99213", 1), ("20610", 2)]

    @pytest.mark.parametrize("value", [450.0, "$450"])
    def test_total_money_rejects_float_and_dollar_strings(self, value):
        with pytest.raises(ValidationError):
            PrecheckExtractionResult.model_validate({"billed_amount_cents": value})


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


class TestClip:
    def test_list_valued_prose_is_joined_not_reprd(self):
        # A model that splits an explanation into sentences must not show the
        # doctor "['First point.', 'Second point.']".
        result = RiskReviewResult.model_validate(
            {"findings": [_finding(explanation=["First point.", 3, "  Second point. "])]}
        )
        assert result.findings[0].explanation == "First point. Second point."

    def test_list_without_text_items_is_none(self):
        result = RiskReviewResult.model_validate({"findings": [_finding(explanation=[1, 2])]})
        assert result.findings[0].explanation is None

    def test_other_scalars_are_still_stringified(self):
        result = RiskReviewResult.model_validate({"findings": [_finding(explanation=42)]})
        assert result.findings[0].explanation == "42"


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

    def test_numeric_value_is_stringified_not_rejected(self):
        # "value": 2 (a JSON number for a unit count) used to fail the whole
        # RiskReviewResult with string_type — one retry burned, then the
        # pre-check errored after extraction and NCCI had already succeeded.
        result = RiskReviewResult.model_validate(
            {
                "findings": [],
                "proposed_edits": [
                    _edit("change_units", value=2),
                    _edit("change_units", value=2.0),  # not a unit count shape
                    _edit("change_units", value=True),
                    _edit("change_code", value=99213),
                ],
            }
        )
        assert [e.value for e in result.proposed_edits] == ["2", None, None, "99213"]

    def test_icd10_shapes_beyond_three_digits_keep_their_value(self):
        # Every injury/poisoning code carries X placeholders and a 7th
        # character, gout/neoplasm categories a letter in position 3, and the
        # U chapter is live — a pattern that drops these loses one-click apply
        # for exactly the Box 21 corrections a review most often proposes.
        result = RiskReviewResult.model_validate(
            {
                "findings": [],
                "proposed_edits": [
                    _edit("change_code", value="S72.001A"),
                    _edit("change_code", value="t36.0x1a"),
                    _edit("change_code", value="M1A.0X0"),
                    _edit("change_code", value="U07.1"),
                    _edit("change_code", value="S72.001AB"),  # too long
                    _edit("change_code", value="1A2"),  # not a code shape
                ],
            }
        )
        assert [e.value for e in result.proposed_edits] == [
            "S72.001A",
            "T36.0X1A",
            "M1A.0X0",
            "U07.1",
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
