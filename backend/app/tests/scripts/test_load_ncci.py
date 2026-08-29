"""Parser and guard tests for the NCCI loader (no network, no DB).

Fixture content is synthetic — fabricated code pairs and values, never excerpts
of the real CMS files (the CPT codes inside them are AMA-licensed, and the repo
takes no PHI/licensed data either way).
"""

import hashlib
import io
import zipfile
from datetime import date

import pytest

from app.scripts.load_ncci import (
    MueRow,
    PtpRow,
    _zip_members,
    check_shrinkage,
    dedupe_ptp,
    discover_mue_url,
    discover_ptp_urls,
    mue_needs_load,
    parse_mue_csv,
    parse_ptp_txt,
)

# Shape-faithful synthetic PTP file: AMA banner, title, wrapped column headings,
# then tab-delimited rows (col1, col2, pre-1996 flag, effective, deletion, CCMI,
# rationale).
_PTP_SAMPLE = (
    "Some Copyright Banner 2026 Synthetic Medical Association\r\n"
    "Column1/Column2 Edits\r\n"
    "Column 1\tColumn 2\t* = in existence\tEffective\tDeletion\tModifier\tPTP Edit Rationale\r\n"
    "\t\tprior to 1996\tDate\tDate\t0=not allowed\t\r\n"
    "\t\t\t\t*=no data\t1=allowed\t\r\n"
    "\t\t\t\t\t9=not applicable\t\r\n"
    "10001\t10002\t*\t20200101\t*\t1\tMisuse of Column Two code\r\n"
    "10001\t10003\t\t20220401\t20260101\t0\tStandards of medical practice\r\n"
    "10004\t10005\t\t20230701\t20230701\t9\tMutually exclusive procedures\r\n"
    "BAD ROW WITH NO TABS\r\n"
    "10006\t10007\t\t20240101\t*\t7\tbogus indicator dropped\r\n"
)

_MUE_SAMPLE = (
    '"CPT is a registered \xae trademark, synthetic banner row"\n'
    '"HCPCS/CPT Code","Practitioner Services MUE Values",'
    '"MUE Adjudication Indicator","MUE Rationale"\n'
    '"10001","2","3 Date of Service Edit: Clinical","Clinical: Data"\n'
    '"10002","1","2 Date of Service Edit: Policy","CMS Policy"\n'
    '"10003","4","1 Line Edit","Code Descriptor / CPT Instruction"\n'
    '"NOTACODE99","4","1 Line Edit","too long, dropped"\n'
    '"10004","x","1 Line Edit","non-integer value dropped"\n'
).encode("latin-1")


def _ptp_zip(quarter: str, version: str, part: int) -> str:
    return f"/files/zip/medicare-ncci-{quarter}-practitioner-ptp-edits-ccipra-{version}-f{part}.zip"


_PTP_PAGE_SAMPLE = (
    f'<a href="/license/ama?file={_ptp_zip("2026q3", "v322r0", 1)}">f1</a>\n'
    f'<a href="/license/ama?file={_ptp_zip("2026q3", "v322r0", 2)}">f2</a>\n'
    f'<a href="{_ptp_zip("2026q2", "v321r1", 1)}">old quarter</a>\n'
    '<a href="/files/zip/medicare-ncci-2026q3-hospital-ptp-edits-ccioph'
    '-v322r0-f1.zip">hospital, ignored</a>\n'
)

_MUE_PAGE_SAMPLE = (
    '<a href="/files/zip/medicare-ncci-2026-q3-practitioner-services'
    '-mue-table.zip">mue</a>\n'
    '<a href="/files/zip/medicare-ncci-2026-q2-practitioner-services'
    '-mue-table.zip">older quarter</a>\n'
    '<a href="/files/zip/medicare-ncci-2026-q3-facility-outpatient-hospital'
    '-services-mue-table.zip">facility, ignored</a>\n'
    '<a href="/files/zip/practitioner-services-mue-quarterly-additions'
    '-deletions-revisions-06012026.zip">change file, ignored</a>\n'
)


class TestParsePtp:
    def test_parses_data_rows_only(self):
        rows = parse_ptp_txt(_PTP_SAMPLE)
        assert len(rows) == 3  # header junk, bad row, and bogus indicator dropped

    def test_star_deletion_is_none(self):
        row = parse_ptp_txt(_PTP_SAMPLE)[0]
        expected = PtpRow("10001", "10002", date(2020, 1, 1), None, 1, "Misuse of Column Two code")
        assert row == expected

    def test_deletion_date_parsed(self):
        row = parse_ptp_txt(_PTP_SAMPLE)[1]
        assert row.deletion_date == date(2026, 1, 1)
        assert row.modifier_indicator == 0

    def test_retroactive_withdrawal_row_retained(self):
        # Indicator-9 rows load (the lookup skips them); the parser keeps them.
        row = parse_ptp_txt(_PTP_SAMPLE)[2]
        assert row.modifier_indicator == 9
        assert row.effective_date == row.deletion_date


class TestParseMue:
    def test_parses_latin1_and_mai_digit(self):
        rows = parse_mue_csv(_MUE_SAMPLE)
        assert rows == [
            MueRow("10001", 2, 3, "Clinical: Data"),
            MueRow("10002", 1, 2, "CMS Policy"),
            MueRow("10003", 4, 1, "Code Descriptor / CPT Instruction"),
        ]


class TestDiscovery:
    def test_ptp_newest_version_selected_and_license_wrapper_unwrapped(self):
        tag, urls = discover_ptp_urls(_PTP_PAGE_SAMPLE)
        assert tag == "2026Q3-v322r0"
        assert urls == [
            f"https://www.cms.gov{_ptp_zip('2026q3', 'v322r0', 1)}",
            f"https://www.cms.gov{_ptp_zip('2026q3', 'v322r0', 2)}",
        ]

    def test_ptp_revision_ten_beats_nine(self):
        # Audit 2026-08-25 L13: max() on the tag string ranked "r9" above
        # "r10". r0 vs r1 cannot tell the two orderings apart; this can.
        page = _PTP_PAGE_SAMPLE + (
            f'<a href="{_ptp_zip("2026q3", "v322r9", 1)}">nine</a>\n'
            f'<a href="{_ptp_zip("2026q3", "v322r10", 1)}">ten</a>\n'
            f'<a href="{_ptp_zip("2026q3", "v322r10", 2)}">ten f2</a>\n'
        )
        tag, urls = discover_ptp_urls(page)
        assert tag == "2026Q3-v322r10"
        assert len(urls) == 2

    def test_ptp_revision_bump_wins(self):
        page = _PTP_PAGE_SAMPLE + (
            '<a href="/files/zip/medicare-ncci-2026q3-practitioner-ptp-edits-'
            'ccipra-v322r1-f1.zip">replacement</a>'
        )
        tag, urls = discover_ptp_urls(page)
        assert tag == "2026Q3-v322r1"
        assert len(urls) == 1

    def test_ptp_none_found_raises(self):
        with pytest.raises(RuntimeError):
            discover_ptp_urls("<html>nothing here</html>")

    def test_mue_practitioner_full_table_newest_quarter(self):
        # Must skip the facility table AND the quarterly-additions change file
        # (which sorted after the full table and was picked by an earlier regex).
        quarter, url = discover_mue_url(_MUE_PAGE_SAMPLE)
        assert quarter == "2026Q3"
        assert url == (
            "https://www.cms.gov/files/zip/"
            "medicare-ncci-2026-q3-practitioner-services-mue-table.zip"
        )

    def test_mue_none_found_raises(self):
        with pytest.raises(RuntimeError):
            discover_mue_url("<html>nothing here</html>")


def _mue_zip(payload: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("synthetic_mue.csv", payload)
    return buf.getvalue()


class TestMueRepublish:
    """Audit 2026-08-28 LOW-21: a mid-quarter CMS republish keeps the file name
    and the quarter; only the bytes change. The quarter key alone skipped it."""

    def test_first_load_of_a_quarter(self):
        assert mue_needs_load(None, _mue_zip(_MUE_SAMPLE))

    def test_unchanged_file_is_skipped(self):
        blob = _mue_zip(_MUE_SAMPLE)
        assert not mue_needs_load(hashlib.sha256(blob).hexdigest(), blob)

    def test_republished_file_reloads_the_quarter(self):
        old = _mue_zip(_MUE_SAMPLE)
        new = _mue_zip(_MUE_SAMPLE + b'"10005","1","1 Line Edit","added mid-quarter"\n')
        assert mue_needs_load(hashlib.sha256(old).hexdigest(), new)
        assert len(parse_mue_csv(_zip_members(new, ".csv")[0])) == 4

    def test_force_reloads_an_unchanged_file(self):
        blob = _mue_zip(_MUE_SAMPLE)
        assert mue_needs_load(hashlib.sha256(blob).hexdigest(), blob, force=True)


class TestGuards:
    def test_dedupe_last_wins(self):
        a = PtpRow("10001", "10002", date(2020, 1, 1), None, 1, "first")
        b = PtpRow("10001", "10002", date(2020, 1, 1), None, 0, "second")
        assert dedupe_ptp([a, b]) == [b]

    def test_shrinkage_refused(self):
        with pytest.raises(SystemExit):
            check_shrinkage(previous=2_600_000, new=2_000_000, kind="ptp")

    def test_shrinkage_tolerates_small_drop_and_no_history(self):
        check_shrinkage(previous=2_600_000, new=2_500_000, kind="ptp")
        check_shrinkage(previous=None, new=5, kind="ptp")
