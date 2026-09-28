"""The rule layer against every Safe Harbor identifier class, 45 CFR
§164.514(b)(2)(i)(A)-(R), in the spellings our documents actually produce:
title-case and ALL-CAPS, labeled and bare, OCR-noisy, with and without a year.

Every fixture is synthetic (hard rule 1). Every test asserts the identifier is
GONE and, where it matters, that the billing vocabulary next to it survived —
a redactor that eats CPT codes fails the corpus as surely as one that leaks a
name. `scan_residual` is checked to be broader than the redactor: whatever the
redactor misses must at least be flagged.
"""

from datetime import date

import pytest

from app.scripts.deidentify import (
    RULESET_VERSION,
    carve_codes,
    deid_year,
    initials_variants,
    latest_year_in,
    redact_text,
    scan_residual,
    split_residual,
)

CODES = frozenset({"99213", "99214", "93306", "73721", "97110"})


def _clean(text: str, known: list | None = None, **kw) -> str:
    out = redact_text(text, known or [], latest_year=2026, known_codes=CODES, **kw)
    assert out is not None
    return out


def _gone(text: str, *leaks: str, known: list | None = None) -> str:
    out = _clean(text, known)
    for leaked in leaks:
        assert leaked not in out, f"{leaked!r} survived: {out!r}"
    precise, _, _ = split_residual(scan_residual(out, CODES))
    assert precise == {}, f"residual after redaction: {precise} in {out!r}"
    return out


def test_ruleset_version_is_pinned():
    assert RULESET_VERSION == "deid_v2"


# --- (A) names -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text, leak",
    [
        ("Patient: JANE DOE", "JANE DOE"),
        ("Patient name: Jane Doe", "Jane Doe"),
        ("Dear Alice Wonderland,", "Alice Wonderland"),
        ("Sincerely,\nBob Builder", "Bob Builder"),
        ("Mr. Okonkwo-Reyes was seen", "Okonkwo-Reyes"),
        ("Dr. Smith reviewed", "Smith"),
        ("Insured: DOE, JANE", "JANE"),
        ("Patient: Doe, Jane Q.", "Jane"),
        ("Beneficiary Jane Q. Doe", "Jane Q. Doe"),
    ],
)
def test_names_in_letter_slots(text, leak):
    _gone(text, leak)


def test_captured_names_and_claim_numbers_are_removed_exactly():
    out = _gone(
        "Appeal for John Q. Public, claim CLM-TEST-0001.",
        "John Q. Public",
        "CLM-TEST-0001",
        known=["John Q. Public", "CLM-TEST-0001"],
    )
    assert "[REDACTED]" in out


def test_captured_value_inside_an_email_does_not_break_the_email_pattern():
    out = _gone("write to jd@example.com or JD", "jd@example.com", "JD", known=["JD"])
    assert "[EMAIL]" in out


# Guidance §3.2: initials are a name derivative and are NOT permitted.
@pytest.mark.parametrize(
    "text",
    [
        "Re: Appeal of Denied Claim #CLM-1 for J.D., DOS 03/15/2026",
        "Re: Appeal of Denied Claim #CLM-1 for JD, DOS 03/15/2026",
        "Patient: J.D.",
        "Patient J. D. was seen",
        "on behalf of our patient, J.D., who",
    ],
)
def test_patient_initials_are_removed(text):
    out = _clean(text, known=initials_variants("J.D."))
    assert "J.D." not in out and " JD" not in out and "J. D." not in out, out


def test_initials_variants_cover_every_spelling():
    assert set(initials_variants("J.D.")) >= {"JD", "J D", "J.D.", "J. D."}
    assert initials_variants(None) == [] and initials_variants("..") == []


def test_clinical_abbreviations_are_not_mistaken_for_initials():
    out = _clean("Patient takes 5 mg p.o. daily, e.g. twice, for MRI and for CT scan")
    assert "p.o." in out and "e.g." in out and "MRI" in out and "CT scan" in out


# --- (B) geography below the state -----------------------------------------------


@pytest.mark.parametrize(
    "text, leak, keep",
    [
        ("lives at 123 Main Street, Springfield, IL 62704", "Main Street", "IL"),
        ("lives at 123 Main Street, Springfield, IL 62704", "Springfield", "IL"),
        ("lives at 123 Main Street, Springfield, IL 62704", "62704", "IL"),
        ("Springfield, IL", "Springfield", "IL"),
        ("Sangamon County resident", "Sangamon", "resident"),
        ("ZIP: 90210", "90210", "ZIP"),
        ("postal code 90210-1234", "90210", "postal"),
        ("P.O. Box 4471, Peoria, IL", "Box 4471", "IL"),
        ("45 Oak Ave Suite 200\nSpringfield, IL 62704", "Oak Ave", "IL"),
    ],
)
def test_geography(text, leak, keep):
    out = _gone(text, leak)
    assert keep in out


def test_state_abbreviation_survives_but_city_does_not():
    out = _clean("Springfield, IL 62704")
    assert out == "[LOCATION], IL [ZIP]"


# --- (C) dates and ages ----------------------------------------------------------------


@pytest.mark.parametrize(
    "text, leak",
    [
        ("DOB 03/15/1980", "03/15/1980"),
        ("on 1980-03-15", "1980-03-15"),
        ("March 5, 2021", "March 5"),
        ("15 Jan 2020", "15 Jan"),
        ("seen 15-Mar-2026", "15-Mar"),
        ("seen Mar-15-2026", "Mar-15"),
        ("since 03/2026", "03/2026"),
        ("since May 2026", "May 2026"),
        ("on 15 Mar 26", "15 Mar"),
        ("seen 15MAR2026", "15MAR2026"),
        ("seen 03 /15/ 1980", "15/ 1980"),
        ("seen 3/15/80", "3/15/80"),
    ],
)
def test_dates_with_a_year(text, leak):
    _gone(text, leak)


# Guidance §3.3: "the day, month, and any other information that is more
# specific than the year" — a month/day with no year is still a date element.
@pytest.mark.parametrize(
    "text, leak",
    [
        ("DOS 03/15", "03/15"),
        ("DOS 3/15 and 3-15", "3/15"),
        ("follow-up March 15", "March 15"),
        ("follow-up on Sept 3rd", "Sept 3"),
        ("the 15th of March", "15th of March"),
        ("the fifteenth of March", "fifteenth of March"),
        ("admitted 12/31, discharged 1/2", "12/31"),
    ],
)
def test_dates_without_a_year(text, leak):
    _gone(text, leak)


def test_a_bare_year_is_permitted():
    out = _clean("service year 2026; policy effective 2025")
    assert "2026" in out and "2025" in out


def test_blood_pressure_and_ratios_survive_the_partial_date_rule():
    assert "120/80" in _clean("BP 120/80")


@pytest.mark.parametrize(
    "text, expect",
    [
        ("a 92-year-old male", "90+"),
        ("age 92", "90+"),
        ("aged: 95", "90+"),
        ("ninety-two years old", "90+"),
        ("one hundred and two years old", "90+"),
        ("a 40 yr old", "40 yr old"),
        ("a 89-year-old", "89-year-old"),
    ],
)
def test_ages_over_89_are_aggregated_and_under_90_kept(text, expect):
    assert expect in _clean(text)


def test_birth_year_implying_age_over_89_is_removed_against_latest_year():
    # Guidance §3.3 example: birth 1910 + service 2010 -> the reader learns ~100.
    out = redact_text("born in 1934; DOS 2026", [], latest_year=2026)
    assert "1934" not in out and "2026" in out
    kept = redact_text("born in 1980; DOS 2026", [], latest_year=2026)
    assert "1980" in kept
    dob = redact_text("DOB: 1936", [], latest_year=2026)
    assert "1936" not in dob


def test_latest_year_reads_structured_and_text_years():
    assert latest_year_in(["seen in 2024 and 2026"], 2025) == 2026
    assert latest_year_in([None, ""], None) == date.today().year


# --- (D)(E)(F)(G) phone, fax, email, SSN ----------------------------------------------


@pytest.mark.parametrize(
    "text, leak",
    [
        ("call (555) 123-4567", "(555) 123-4567"),
        ("call 555.123.4567", "555.123.4567"),
        ("call +1 555 123 4567", "555 123 4567"),
        ("fax: 555-123-4567", "555-123-4567"),
        ("tel 555-1234", "555-1234"),
        ("mail a@b.com", "a@b.com"),
        ("SSN 000-00-0000", "000-00-0000"),
        ("SSN 000 00 0000", "000 00 0000"),
        ("SSN 000000000", "000000000"),
    ],
)
def test_contact_and_ssn(text, leak):
    _gone(text, leak)


# --- (H)(I)(J)(K)(L)(M)(R) numbers, licences, vehicles, devices, other codes --------------


@pytest.mark.parametrize(
    "text, leak",
    [
        ("MRN: 48213", "48213"),
        ("MRN 4821399", "4821399"),
        ("Medical Record No. 7712", "7712"),
        ("Acct # 9921", "9921"),
        ("Account number 55-8812", "55-8812"),
        ("Patient ID: P-4471", "P-4471"),
        ("Lic. A12345", "A12345"),
        ("License # MD-55123", "MD-55123"),
        ("DEA AB1234563", "AB1234563"),
        ("NPI 1234567890", "1234567890"),
        ("Tax ID 12-3456789", "12-3456789"),
        ("Group 5521 Policy 77A", "5521"),
        ("Group 5521 Policy 77A", "77A"),
        ("MBI 1EG4-TE5-MK73", "1EG4-TE5-MK73"),
        ("Member ID W1A2B3C4D", "W1A2B3C4D"),
        ("Subscriber ABC123456789", "ABC123456789"),
        ("VIN 1HGCM82633A004352", "1HGCM82633A004352"),
        ("plate ABC1234", "ABC1234"),
        ("serial SN-88213-Q", "88213"),
        ("Device ID: DV-99-Q7", "DV-99-Q7"),
        ("Auth #: AUTH-555", "AUTH-555"),
        ("ref CASE-1234", "CASE-1234"),
        ("Claim # 20260315001", "20260315001"),
        ("Encounter 4412-A", "4412-A"),
        ("member w1a2b3c4d auth ref Auth-55512", "w1a2b3c4d"),
    ],
)
def test_labeled_and_shaped_identifiers(text, leak):
    _gone(text, leak)


def test_prose_uses_of_the_cue_words_survive():
    out = _clean("a member of the plan; the account manager; the case was reviewed")
    assert out == "a member of the plan; the account manager; the case was reviewed"


def test_member_id_redaction_survives_an_empty_key_set():
    """Exactly the production condition past the 30-day archive window: the raw
    member id is not in `known`, so the shape rules must carry it."""
    out = redact_text("Subscriber W1A2B3C4D, claim CLM-TEST-0001.", [None, None])
    assert "W1A2B3C4D" not in out and "CLM-TEST-0001" not in out


# --- (N)(O) URLs and IP addresses -------------------------------------------------------


@pytest.mark.parametrize(
    "text, leak",
    [
        ("see www.example.com/x", "example.com"),
        ("see https://portal.example.com/claims?id=1", "portal.example.com"),
        ("from 10.0.0.1", "10.0.0.1"),
        ("from fe80::1ff:fe23:4567:890a", "fe23"),
    ],
)
def test_urls_and_ips(text, leak):
    _gone(text, leak)


# --- (A)/(R) employer and occupation ------------------------------------------------------


@pytest.mark.parametrize(
    "text, leak",
    [
        ("employer: Acme Widgets Inc", "Acme"),
        ("employed by Springfield Steel", "Springfield Steel"),
        ("works at Central High School", "Central High"),
        ("occupation: teacher", "teacher"),
        ("works as a school bus driver", "bus driver"),
        ("is employed as an accountant", "accountant"),
    ],
)
def test_employer_and_occupation(text, leak):
    _gone(text, leak)


# --- five-digit runs: CPT versus ZIP ---------------------------------------------------


def test_known_cpt_codes_survive_and_unknown_five_digit_runs_do_not():
    out = _clean("billed 99213 and 93306; lives in 90210; code 73721; charge $45,000.00; 45000")
    assert "99213" in out and "93306" in out and "73721" in out
    assert "90210" not in out and " 45000" not in out
    assert "$45,000.00" in out


def test_cued_codes_survive_without_the_ncci_set():
    out = redact_text("CPT 99213, 99214 and 93306 were denied; E/M 99215", [], known_codes=None)
    assert "99213" in out and "99214" in out and "93306" in out and "99215" in out


def test_billing_vocabulary_is_preserved_end_to_end():
    text = (
        "We appeal the denial of CPT 73721 billed on the original claim (CMS-1500) for "
        "ICD-10-CM M17.11; E/M 99214 with modifier 25 was distinct. CARC CO-197, RARC "
        "N115, M76, MA13; HCPCS J1234; POS 11; UB-04; Dx I48.91 and M23.205."
    )
    out = _clean(text)
    for keep in (
        "73721",
        "CMS-1500",
        "M17.11",
        "99214",
        "25",
        "CO-197",
        "N115",
        "M76",
        "MA13",
        "J1234",
        "POS 11",
        "UB-04",
        "I48.91",
        "M23.205",
    ):
        assert keep in out, keep
    precise, review, names = split_residual(scan_residual(out, CODES))
    assert precise == {}
    assert review.get("alnum_id_like")  # CMS-1500 / ICD-10-CM: review, not a leak


# --- residual scanner -----------------------------------------------------------------------


def test_scan_residual_flags_leaks_and_candidate_names():
    flags = scan_residual("Leftover a@b.com and Zorp Yelling here")
    assert flags.get("email") == 1
    assert "Zorp Yelling" in flags.get("candidate_names", [])
    assert scan_residual("fully clean text") == {}


@pytest.mark.parametrize(
    "text, kind",
    [
        ("leftover W1A2B3C4D", "member_alnum"),
        ("leftover 1EG4-TE5-MK73", "mbi"),
        ("DOS 03/15", "partial_date"),
        ("MRN: 48213", "labeled_id"),
        ("Tax ID 12-3456789", "tax_id"),
        ("Sangamon County", "county"),
        ("for J.D., DOS", "initials"),
        ("employer: Acme", "employer"),
        ("IL 62704", "state_zip"),
        ("lives in 90210", "zip_like"),
    ],
)
def test_scan_residual_is_broader_than_the_redactor(text, kind):
    assert scan_residual(text, CODES).get(kind), scan_residual(text, CODES)


def test_five_digit_runs_are_review_only_without_the_code_set_and_precise_with_it():
    assert "zip_like_uncertain" in scan_residual("lives in 90210")
    assert scan_residual("lives in 90210", CODES).get("zip_like") == 1
    assert "zip_like" not in scan_residual("CPT 99213", CODES)


def test_split_residual_partitions_precise_review_and_names():
    precise, review, names = split_residual(
        {"email": 1, "mbi": 2, "alnum_id_like": 3, "candidate_names": ["Zorp"]}
    )
    assert precise == {"email": 1, "mbi": 2}
    assert review == {"alnum_id_like": 3}
    assert names == ["Zorp"]
    assert split_residual({}) == ({}, {}, [])


def test_residual_scanner_ignores_placeholder_tokens():
    out = _clean("employer: Acme Widgets; works as a nurse; Patient J.D. seen", known=["J.D."])
    assert scan_residual(out, CODES).get("employer") is None
    assert scan_residual(out, CODES).get("initials") is None


# --- helpers -------------------------------------------------------------------------------------


def test_deid_year():
    assert deid_year(date(1980, 3, 15)) == 1980
    assert deid_year(None) is None


def test_carve_codes_keeps_codes_and_drops_punctuation_remnants():
    text = "Mary Chen I48.91 (M23.205)"
    assert carve_codes([(0, len(text))], text) == [(0, 10)]
    assert carve_codes([(10, 16)], text) == []


def test_none_and_empty_pass_through():
    assert redact_text(None, []) is None
    assert redact_text("", []) == ""
    assert scan_residual(None) == {} and scan_residual("") == {}
