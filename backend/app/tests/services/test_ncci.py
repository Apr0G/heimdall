"""Unit tests for the NCCI evaluation rules (pure functions — no DB, no AWS).

Codes are synthetic (hard rule 1); the semantics under test are the NCCI Policy
Manual Ch. 1 rules: modifier indicator 0/1 dispositions (indicator 9 and the
[effective, deletion) active window are filtered in SQL by ptp_conflicts), the
associated-modifier list, and MAI 1 vs 2/3 unit arithmetic.
"""

from datetime import date
from types import SimpleNamespace

from app.services.analysis import co97_note, has_co97
from app.services.ncci import (
    NCCI_ASSOCIATED_MODIFIERS,
    ClaimLine,
    PtpFinding,
    evaluate_mue,
    normalize_code,
    ptp_bypassed,
    ptp_indicator_for_pair,
)


class TestNormalizeCode:
    def test_strips_and_uppercases(self):
        assert normalize_code("  99213 ") == "99213"
        assert normalize_code("g0008") == "G0008"

    def test_drops_appended_modifier(self):
        assert normalize_code("99213-25") == "99213"
        assert normalize_code("99213 25") == "99213"

    def test_empty(self):
        assert normalize_code("") == ""


class TestPtpBypassed:
    def test_indicator_0_never_bypassed(self):
        assert not ptp_bypassed(0, [("59", "XE", "LT")])

    def test_indicator_1_bypassed_with_associated_modifier(self):
        for modifier in ("59", "XE", "XS", "XP", "XU", "25", "LT", "F5", "91"):
            assert ptp_bypassed(1, [(modifier,)]), modifier

    def test_indicator_1_not_bypassed_without_modifier(self):
        assert not ptp_bypassed(1, [()])
        assert not ptp_bypassed(1, [])

    def test_non_associated_modifiers_do_not_bypass(self):
        # Ch. 1 Sec. E explicitly excludes 22, 76, 77.
        for modifier in ("22", "76", "77", "GA"):
            assert not ptp_bypassed(1, [(modifier,)]), modifier

    def test_every_column2_line_must_carry_a_modifier(self):
        # One modified line must not mark an unmodified same-code line as
        # bypassed: that line will still deny.
        assert ptp_bypassed(1, [("59",), ("XS",)])
        assert not ptp_bypassed(1, [("59",), ()])

    def test_associated_list_shape(self):
        assert {"59", "XE", "XS", "XP", "XU", "25", "57", "91", "RT", "LT"} <= (
            NCCI_ASSOCIATED_MODIFIERS
        )
        assert {"22", "76", "77"}.isdisjoint(NCCI_ASSOCIATED_MODIFIERS)


class TestEvaluateMue:
    def test_within_limit(self):
        lines = [ClaimLine(cpt="99999", units=2)]
        assert evaluate_mue("99999", lines, mue_value=2, mai=1) is None

    def test_mai_1_judges_lines_separately(self):
        # Two lines of 2 units, MUE 3: no single line exceeds — MAI 1 passes
        # (line splitting with modifiers is exactly how MAI 1 is worked).
        lines = [ClaimLine(cpt="99999", units=2), ClaimLine(cpt="99999", units=2)]
        assert evaluate_mue("99999", lines, mue_value=3, mai=1) is None
        assert evaluate_mue("99999", lines, mue_value=1, mai=1) == 2

    def test_mai_2_and_3_sum_across_lines(self):
        lines = [ClaimLine(cpt="99999", units=2), ClaimLine(cpt="99999", units=2)]
        for mai in (2, 3):
            assert evaluate_mue("99999", lines, mue_value=3, mai=mai) == 4

    def test_other_codes_ignored(self):
        lines = [ClaimLine(cpt="11111", units=99)]
        assert evaluate_mue("99999", lines, mue_value=1, mai=2) is None


class TestCo97Annotation:
    def test_detects_co97_spellings(self):
        assert has_co97(["CO-97"])
        assert has_co97(["co 97"])
        assert has_co97(["97"], ["CO"])

    def test_ignores_other_codes_and_groups(self):
        assert not has_co97(["CO-50"])
        assert not has_co97(["97"], ["PR"])  # PR-97 is not the bundling denial
        assert not has_co97(None)

    def test_note_wording_by_indicator(self):
        overridable = PtpFinding("11111", "22222", 1, None, False)
        blocked = PtpFinding("11111", "22222", 0, None, False)
        note = co97_note([overridable])
        assert note is not None and "OVERRIDABLE" in note and "22222" in note
        note = co97_note([blocked])
        assert note is not None and "NOT overridable" in note

    def test_no_findings_keeps_manual_wording(self):
        # None → caller leaves the prompt's manual-verification text untouched.
        assert co97_note([]) is None


class TestPtpIndicatorForPair:
    """The appeal-side lookup. Unlike the pre-check, an appeal concerns a claim
    already adjudicated on its real DOS — evaluating against today's table
    when that date is unknown would assert an indicator for the wrong quarter."""

    async def test_unknown_dos_returns_none_without_querying(self):
        class _NoQuery:
            async def scalar(self, stmt):
                raise AssertionError("must not consult the table without a date of service")

        assert await ptp_indicator_for_pair(_NoQuery(), "11111", "22222", None) is None

    async def test_known_dos_queries_and_maps_the_row(self):
        row = SimpleNamespace(
            column1="11111", column2="22222", modifier_indicator=1, rationale=None
        )

        class _OneRow:
            async def scalar(self, stmt):
                return row

        hit = await ptp_indicator_for_pair(_OneRow(), "11111", "22222", date(2026, 1, 15))
        assert (hit.column1, hit.column2, hit.modifier_indicator, hit.bypassed) == (
            "11111",
            "22222",
            1,
            False,
        )

    async def test_no_findings_when_dos_unknown_keeps_manual_wording(self):
        # End to end: no DOS -> no finding -> co97_note is None -> the prompt's
        # "check the indicator manually" text stands.
        class _NoQuery:
            async def scalar(self, stmt):
                raise AssertionError("must not query")

        hit = await ptp_indicator_for_pair(_NoQuery(), "11111", "22222", None)
        assert co97_note([h for h in [hit] if h is not None]) is None
