"""Risk-engine policy tests: band derivation, deterministic finding mapping,
and the claim-line bridge from stored extraction JSON. Pure functions only —
codes are synthetic (hard rule 1)."""

from types import SimpleNamespace

from app.services.ncci import MueFinding, NcciResult, PtpFinding
from app.services.precheck import (
    claim_lines_from_extraction,
    derive_band,
    deterministic_edits,
    deterministic_findings,
)


class TestDeriveBand:
    def test_priority(self):
        assert derive_band([{"severity": "low"}, {"severity": "high"}]) == "high"
        assert derive_band([{"severity": "medium"}, {"severity": "info"}]) == "moderate"
        assert derive_band([{"severity": "info"}]) == "low"
        assert derive_band([]) is None


class TestDeterministicFindings:
    def test_no_data_yields_only_the_skip_notice(self):
        findings = deterministic_findings(NcciResult(), dos_missing=True)
        assert [f["check_id"] for f in findings] == ["ncci_unavailable"]
        assert findings[0]["severity"] == "info"

    def test_dos_missing_notice_when_data_available(self):
        result = NcciResult(version_tag="ptp x / mue y", data_available=True)
        findings = deterministic_findings(result, dos_missing=True)
        assert [f["check_id"] for f in findings] == ["dos_missing"]

    def test_ptp_severity_by_disposition(self):
        result = NcciResult(
            ptp=(
                PtpFinding("11111", "22222", 1, "rationale", bypassed=True),
                PtpFinding("11111", "33333", 1, None, bypassed=False),
                PtpFinding("11111", "44444", 0, None, bypassed=False),
            ),
            version_tag="v",
            data_available=True,
        )
        findings = deterministic_findings(result, dos_missing=False)
        by_title_code = {f["title"].split()[0]: f for f in findings}
        assert by_title_code["22222"]["severity"] == "info"  # bypassed by modifier
        assert by_title_code["33333"]["severity"] == "high"  # missing modifier
        assert by_title_code["33333"]["predicted_carc"] == "CO-97"
        assert by_title_code["44444"]["severity"] == "high"  # never bypassable
        assert all(f["source"] == "ncci" for f in by_title_code.values())

    def test_mue_severity_by_mai(self):
        result = NcciResult(
            mue=(
                MueFinding("55555", 4, 2, 2, None),  # MAI 2: policy-absolute
                MueFinding("66666", 4, 2, 3, None),  # MAI 3: clinical
                MueFinding("77777", 4, 2, 1, None),  # MAI 1: line edit
            ),
            version_tag="v",
            data_available=True,
        )
        severities = {
            f["title"].split(":")[0]: f["severity"]
            for f in deterministic_findings(result, dos_missing=False)
        }
        assert severities == {"55555": "high", "66666": "medium", "77777": "medium"}


class TestDeterministicEdits:
    def test_ptp_dispositions_map_to_diff_lines(self):
        result = NcciResult(
            ptp=(
                PtpFinding("11111", "22222", 1, None, bypassed=True),  # no edit needed
                PtpFinding("11111", "33333", 1, None, bypassed=False),  # add modifier
                PtpFinding("11111", "44444", 0, None, bypassed=False),  # remove line
            ),
            mue=(MueFinding("55555", 4, 2, 3, None),),
            version_tag="v",
            data_available=True,
        )
        edits = deterministic_edits(result)
        assert [(e["kind"], e["target"]) for e in edits] == [
            ("add_modifier", "33333"),
            ("remove_line", "44444"),
            ("change_units", "55555"),
        ]
        assert all(e["source"] == "ncci" for e in edits)
        assert "≤2 units/day" in edits[2]["instruction"]

    def test_no_data_no_edits(self):
        assert deterministic_edits(NcciResult()) == []


class TestClaimLineBridge:
    def test_reads_lines_from_extracted_json(self):
        extraction = SimpleNamespace(
            extracted_json={
                "claim_lines": [
                    {"cpt": "99213", "modifiers": ["25"], "units": 1},
                    {"cpt": "11111", "modifiers": [], "units": 2},
                    {"cpt": "  ", "modifiers": [], "units": 1},  # blank -> skipped
                    "not-a-dict",
                ]
            }
        )
        lines = claim_lines_from_extraction(extraction)
        assert [(line.cpt, line.modifiers, line.units) for line in lines] == [
            ("99213", ("25",), 1),
            ("11111", (), 2),
        ]

    def test_missing_json_is_empty(self):
        assert claim_lines_from_extraction(SimpleNamespace(extracted_json=None)) == []
