"""Keyed hashing of PHI-derived identifiers (MED-19, MED-24)."""

import hashlib

import pytest

from app.core import hashing

_PEPPER = "test-pepper-not-a-real-secret"
_MEMBER = "W1A2B3C4D"


@pytest.fixture
def pepper(monkeypatch):
    monkeypatch.setattr(hashing.settings, "phi_hash_pepper", _PEPPER)


def test_fails_closed_without_a_pepper(monkeypatch):
    """Never silently degrade to an unkeyed digest: it looks identical in the
    database while providing none of the protection."""
    monkeypatch.setattr(hashing.settings, "phi_hash_pepper", "")
    assert hashing.is_configured() is False
    with pytest.raises(hashing.PepperMissingError):
        hashing.keyed_hash(_MEMBER, purpose=hashing.MEMBER_ID)


def test_whitespace_only_pepper_is_treated_as_missing(monkeypatch):
    monkeypatch.setattr(hashing.settings, "phi_hash_pepper", "   ")
    assert hashing.is_configured() is False
    with pytest.raises(hashing.PepperMissingError):
        hashing.keyed_hash(_MEMBER, purpose=hashing.MEMBER_ID)


def test_is_not_a_bare_digest(pepper):
    """Member IDs are short, structured and payer-prefixed — a plain SHA-256 is
    exhaustible offline, so a DB dump alone would recover every raw identifier."""
    bare = hashlib.sha256(_MEMBER.lower().encode()).hexdigest()
    assert hashing.keyed_hash(_MEMBER, purpose=hashing.MEMBER_ID) != bare


def test_is_deterministic_and_case_insensitive(pepper):
    a = hashing.keyed_hash(_MEMBER, purpose=hashing.MEMBER_ID)
    b = hashing.keyed_hash(f"  {_MEMBER.lower()}  ", purpose=hashing.MEMBER_ID)
    assert a == b


def test_purposes_are_domain_separated(pepper):
    """The same input under two purposes must not collide, or a member_id_hash
    could be correlated against a digest made for any other purpose."""
    assert hashing.keyed_hash("X", purpose=hashing.MEMBER_ID) != hashing.keyed_hash(
        "X", purpose="some_other_purpose"
    )


def test_scope_prevents_cross_tenant_correlation(pepper):
    """Without per-practice scoping, an identical hash under two practices proves
    the same member is at both — a linkage the tenancy model otherwise forbids."""
    practice_a = "11111111-1111-1111-1111-111111111111"
    practice_b = "22222222-2222-2222-2222-222222222222"
    assert hashing.keyed_hash(
        _MEMBER, purpose=hashing.MEMBER_ID, scope=practice_a
    ) != hashing.keyed_hash(_MEMBER, purpose=hashing.MEMBER_ID, scope=practice_b)


def test_rotating_the_pepper_changes_every_digest(monkeypatch, pepper):
    before = hashing.keyed_hash(_MEMBER, purpose=hashing.MEMBER_ID)
    monkeypatch.setattr(hashing.settings, "phi_hash_pepper", "rotated-pepper")
    assert hashing.keyed_hash(_MEMBER, purpose=hashing.MEMBER_ID) != before
