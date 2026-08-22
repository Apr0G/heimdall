"""The one-time code store: single use, attempt cap, expiry, per-email replace."""

import pytest

from app.services import recovery_codes as rc


@pytest.fixture(autouse=True)
def _memory_store(monkeypatch):
    monkeypatch.setattr(rc, "_store", rc._MemoryStore())


def test_code_is_six_digits_and_single_use():
    code = rc.issue_code("a@b.com")
    assert len(code) == 6 and code.isdigit()
    assert rc.verify_code("a@b.com", code) is True
    assert rc.verify_code("a@b.com", code) is False  # consumed


def test_wrong_guesses_are_capped(monkeypatch):
    monkeypatch.setattr(rc.settings, "mfa_recovery_max_attempts", 3)
    code = rc.issue_code("a@b.com")
    wrong = "000000" if code != "000000" else "111111"
    assert rc.verify_code("a@b.com", wrong) is False
    assert rc.verify_code("a@b.com", wrong) is False
    assert rc.verify_code("a@b.com", wrong) is False  # third strike voids it
    assert rc.verify_code("a@b.com", code) is False


def test_new_request_replaces_old_code(monkeypatch):
    # Deterministic, distinct codes so the replacement property is asserted
    # unconditionally (a cached-code regression would previously have passed).
    draws = iter([111111, 222222])
    monkeypatch.setattr(rc.secrets, "randbelow", lambda n: next(draws))
    first = rc.issue_code("a@b.com")
    second = rc.issue_code("a@b.com")
    assert (first, second) == ("111111", "222222")
    assert rc.verify_code("a@b.com", first) is False
    assert rc.verify_code("a@b.com", second) is True


def test_codes_are_per_email():
    code = rc.issue_code("a@b.com")
    assert rc.verify_code("other@b.com", code) is False
    assert rc.verify_code("a@b.com", code) is True


def test_expiry(monkeypatch):
    store = rc._MemoryStore()
    monkeypatch.setattr(rc, "_store", store)
    now = [1000.0]
    monkeypatch.setattr(rc.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(rc.settings, "mfa_recovery_code_ttl_seconds", 60)
    code = rc.issue_code("a@b.com")
    now[0] += 61
    assert rc.verify_code("a@b.com", code) is False
