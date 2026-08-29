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


def test_a_wrong_guess_does_not_extend_the_codes_life(monkeypatch):
    # Audit 2026-08-25 L6: a wrong guess used to re-write the record and re-arm
    # its full TTL, so an attacker could keep a code alive by guessing. The
    # record is immutable now; attempts live in their own key.
    store = rc._MemoryStore()
    monkeypatch.setattr(rc, "_store", store)
    now = [1000.0]
    monkeypatch.setattr(rc.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(rc.settings, "mfa_recovery_code_ttl_seconds", 60)
    monkeypatch.setattr(rc.settings, "mfa_recovery_max_attempts", 5)
    code = rc.issue_code("a@b.com")
    wrong = "000000" if code != "000000" else "111111"
    now[0] += 50
    assert rc.verify_code("a@b.com", wrong) is False
    now[0] += 11  # 61s after issue: dead regardless of the guess at 50s
    assert rc.verify_code("a@b.com", code) is False


def test_redis_store_counts_attempts_with_one_atomic_incr(monkeypatch):
    # Audit 2026-08-25 M4: the counter was a read-modify-write that concurrent
    # guesses could race past. Production uses a server-side INCR + EXPIRE in
    # one pipeline; pin that shape without a Redis.
    calls: list = []

    class Pipe:
        def incr(self, key):
            calls.append(("incr", key))

        def expire(self, key, ttl):
            calls.append(("expire", key, ttl))

        def execute(self):
            return [3, True]

    class FakeRedis:
        def pipeline(self):
            return Pipe()

    store = rc._RedisStore.__new__(rc._RedisStore)
    store._r = FakeRedis()
    assert store.incr("attempts:a@b.com", 60) == 3
    assert calls == [("incr", "attempts:a@b.com"), ("expire", "attempts:a@b.com", 60)]
