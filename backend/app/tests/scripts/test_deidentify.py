from datetime import date

import pytest

from app.scripts.deidentify import deid_year, hash_ref, redact_text


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
