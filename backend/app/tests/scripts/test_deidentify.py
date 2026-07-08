from datetime import date

import pytest

from app.scripts.deidentify import deid_year, hash_ref, redact_text, scan_residual


def test_redacts_formatted_phi():
    text = "SSN 123-45-6789, call (555) 123-4567 or a@b.com on 03/15/1980, id 123456789"
    out = redact_text(text, [])
    for leaked in ("123-45-6789", "(555) 123-4567", "a@b.com", "03/15/1980", "123456789"):
        assert leaked not in out
    assert "[SSN]" in out and "[PHONE]" in out and "[EMAIL]" in out and "[DATE]" in out


def test_redacts_captured_identifiers():
    out = redact_text("Appeal for John Q. Public, claim CLM-99.", ["John Q. Public", "CLM-99"])
    assert "John Q. Public" not in out and "CLM-99" not in out


def test_redacts_letter_name_slots():
    out = redact_text("Dear Alice Wonderland,\n...\nSincerely,\nBob Builder", [])
    assert "Alice Wonderland" not in out and "Bob Builder" not in out


def test_preserves_billing_codes():
    # Codes are training signal, not PHI — must survive redaction.
    out = redact_text("CPT 99213 denied under CO-197, ICD J45.909", [])
    assert "99213" in out and "CO-197" in out and "J45.909" in out


def test_redacts_auth_numbers_but_keeps_form_and_carc_codes():
    out = redact_text("Auth #: AUTH-555 for CMS-1500 claim under CO-197, UB-04", [])
    assert "AUTH-555" not in out
    assert "CMS-1500" in out and "CO-197" in out and "UB-04" in out


def test_redacts_geography_ip_and_ages():
    out = redact_text(
        "123 Main Street, City, CA 90210. IP 10.0.0.1. A 92-year-old; a 40 yr old.", []
    )
    for leaked in ("Main Street", "90210", "10.0.0.1"):
        assert leaked not in out
    assert "90+" in out and "40 yr old" in out  # >=90 aggregated, <90 kept
    assert "CA" in out  # state is allowed under Safe Harbor


def test_redacts_many_date_formats():
    out = redact_text("on 1980-03-15 and March 5, 2021 and 15 Jan 2020", [])
    for leaked in ("1980-03-15", "March 5, 2021", "15 Jan 2020"):
        assert leaked not in out


def test_scan_residual_flags_leaks_and_candidates():
    flags = scan_residual("Leftover a@b.com and Zorp Yelling here")
    assert flags.get("email") == 1
    assert "Zorp Yelling" in flags.get("candidate_names", [])
    assert scan_residual("fully clean text") == {}


def test_helpers():
    assert deid_year(date(1980, 3, 15)) == 1980
    assert deid_year(None) is None
    assert hash_ref("CLM-1").startswith("ref_") and hash_ref("CLM-1") == hash_ref("clm-1")


def test_ner_catches_free_floating_names_and_keeps_codes():
    # Skips in CI (Presidio not installed there); runs where it is.
    pytest.importorskip("presidio_analyzer")
    out = redact_text("The report for Jane Doe was reviewed in Boston.", [], use_ner=True)
    assert "Jane Doe" not in out and "Boston" not in out
    codes = redact_text("CPT 99213 denied under CO-197, ICD J45.909", [], use_ner=True)
    assert "99213" in codes and "CO-197" in codes and "J45.909" in codes


def test_ner_keeps_alphanumeric_diagnosis_codes():
    # NER mis-tags codes like I48.91 as a PERSON; they must survive regardless.
    pytest.importorskip("presidio_analyzer")
    out = redact_text("Dx I48.91 and M23.205 support CPT 93306 for Mary Chen.", [], use_ner=True)
    assert "I48.91" in out and "M23.205" in out and "93306" in out
    assert "Mary Chen" not in out
