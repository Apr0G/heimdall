from datetime import date

import pytest

from app.core import hashing
from app.scripts.deidentify import (
    deid_year,
    hash_ref,
    redact_text,
    scan_residual,
    split_residual,
)


@pytest.fixture
def pepper(monkeypatch):
    """hash_ref is HMAC-keyed and fails closed without a pepper (§164.514(c))."""
    monkeypatch.setattr(hashing.settings, "phi_hash_pepper", "test-pepper-not-a-real-secret")


def test_redacts_formatted_phi():
    # Synthetic SSN per hard rule 1 — 000-00-0000, never a realistic-looking one.
    text = "SSN 000-00-0000, call (555) 123-4567 or a@b.com on 03/15/1980, id 123456789"
    out = redact_text(text, [])
    for leaked in (
        "000-00-0000",
        "(555) 123-4567",
        "a@b.com",
        "03/15/1980",
        "123456789",
    ):
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


def test_helpers(pepper):
    assert deid_year(date(1980, 3, 15)) == 1980
    assert deid_year(None) is None
    assert hash_ref("CLM-1").startswith("ref_") and hash_ref("CLM-1") == hash_ref("clm-1")


# --- HIGH-05: member IDs are redacted structurally ---------------------------
#
# The export built its exact-match key-set from extracted_json["member_id"], but
# that JSON is written with exclude={"member_id"} per hard rule 5 — so the lookup
# returned None for every case and the member ID was never redacted at all. These
# patterns are the layer that does not depend on having captured the value.


@pytest.mark.parametrize(
    "member_id",
    ["1EG4-TE5-MK73", "1EG4TE5MK73", "W1A2B3C4D", "ABC123456789", "XYZW00112233"],
    ids=[
        "mbi-dashed",
        "mbi-plain",
        "commercial-short",
        "commercial-long",
        "commercial-mixed",
    ],
)
def test_member_id_shapes_are_redacted_without_being_captured(member_id):
    out = redact_text(f"Member ID {member_id} was denied.", [])
    assert member_id not in out
    assert "[MEMBER_ID]" in out or "[ID]" in out


def test_member_id_redaction_survives_an_empty_key_set():
    """Exactly the production condition: known=[...None...] because the raw value
    was excluded from the archived JSON by design."""
    out = redact_text("Subscriber W1A2B3C4D, claim CLM-TEST-0001.", [None, None])
    assert "W1A2B3C4D" not in out


def test_member_patterns_do_not_eat_billing_codes():
    """CPT/ICD/HCPCS/CARC/NPI must survive as training signal."""
    out = redact_text("CPT 99213, ICD J45.909, HCPCS J1234, CARC CO-197, POS 11", [])
    for keep in ("99213", "J45.909", "J1234", "CO-197", "11"):
        assert keep in out


def test_scan_residual_flags_surviving_member_ids():
    assert scan_residual("leftover W1A2B3C4D").get("member_alnum") == 1
    assert scan_residual("leftover 1EG4-TE5-MK73").get("mbi") == 1


# --- MED-24: the re-identification code must be keyed ------------------------


def test_hash_ref_fails_closed_without_a_pepper(monkeypatch):
    """§164.514(c) requires a code NOT derived from information about the
    individual. An unkeyed sha256(claim_number) is derived from exactly that, so
    silently falling back to one would look identical while protecting nothing."""
    monkeypatch.setattr(hashing.settings, "phi_hash_pepper", "")
    with pytest.raises(hashing.PepperMissingError):
        hash_ref("CLM-TEST-0001")


def test_hash_ref_is_not_a_bare_sha256(pepper):
    """Anyone holding an EOB could otherwise compute the digest offline and
    confirm the case is in the corpus."""
    import hashlib

    claim = "CLM-TEST-0001"
    bare = "ref_" + hashlib.sha256(claim.strip().lower().encode()).hexdigest()[:12]
    assert hash_ref(claim) != bare


def test_hash_ref_changes_with_the_pepper(monkeypatch, pepper):
    first = hash_ref("CLM-TEST-0001")
    monkeypatch.setattr(hashing.settings, "phi_hash_pepper", "a-different-pepper")
    assert hash_ref("CLM-TEST-0001") != first


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


def test_ner_keeps_rarc_codes():
    # RARC remark codes (N115, M76, MA13) get NER-tagged as a PERSON; must survive.
    pytest.importorskip("presidio_analyzer")
    out = redact_text("CARC CO-50 with RARC N115, M76, and MA13 denied John Roe.", [], use_ner=True)
    assert "N115" in out and "M76" in out and "MA13" in out and "CO-50" in out
    assert "John Roe" not in out


@pytest.mark.parametrize(
    "text",
    ["seen 15-Mar-2026", "seen Mar-15-2026", "since 03/2026", "since May 2026", "on 15 Mar 26"],
)
def test_date_variants_are_redacted_or_flagged(text):
    """Audit MED-15: these spellings previously survived both redaction and the
    residual scan. Whichever layer catches them, none may pass silently."""
    out = redact_text(text, known=[])
    assert "2026" not in out or scan_residual(out).get("date")


def test_mixed_case_member_and_auth_ids_are_redacted():
    out = redact_text("member w1a2b3c4d auth ref Auth-55512", known=[])
    assert "w1a2b3c4d" not in out and "Auth-55512" not in out


def test_residual_scanner_is_broader_than_redactor():
    # A bare ZIP is not redacted (5-digit runs are CPT codes too) but the
    # independent residual detector must still raise it for review.
    out = redact_text("ZIP: 90210", known=[])
    assert scan_residual(out).get("zip_like")


def test_billing_vocabulary_is_a_review_flag_not_a_leak():
    """The letter prompt tells the model to cite CPT codes and "the original
    claim (CMS-1500)"; the broad ZIP / letter+digit detectors fire on both.
    They are review counts — a gate that aborted on them refused every real
    corpus, and the only way past it also disabled the candidate-name gate."""
    out = redact_text(
        "We appeal the denial of CPT 73721 billed on the original claim (CMS-1500) "
        "for ICD-10-CM M17.11; E/M 99214 with modifier 25 was distinct.",
        [],
    )
    precise, review, names = split_residual(scan_residual(out))
    assert precise == {}
    assert review.get("zip_like") and review.get("alnum_id_like")
    assert "Jane" not in " ".join(names)


def test_split_residual_keeps_the_precise_detectors_fatal():
    precise, review, names = split_residual(
        {"email": 1, "mbi": 2, "zip_like": 5, "alnum_id_like": 3, "candidate_names": ["Zorp"]}
    )
    assert precise == {"email": 1, "mbi": 2}
    assert review == {"zip_like": 5, "alnum_id_like": 3}
    assert names == ["Zorp"]
    assert split_residual({}) == ({}, {}, [])
