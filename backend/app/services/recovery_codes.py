"""One-time email codes for authenticator recovery.

Synchronous (redis-py); call via a threadpool from async code.

Codes live in Redis in production (shared across API tasks) and in-process when
REDIS_URL is unset (single-process dev/test only — the same split as the rate
limiter). Only a salted SHA-256 of the code is stored, it expires on its own, a
wrong guess burns one of a small number of attempts, and a correct guess
consumes it. Keys are per email so a fresh request always replaces the old code.
"""

import hashlib
import json
import secrets
import threading
import time

from app.core.config import settings

_PREFIX = "mfa-recover:"
_ATTEMPTS_PREFIX = "mfa-recover-attempts:"


def _hash(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


class _MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, value)

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            if item[0] < time.monotonic():
                del self._data[key]
                return None
            return item[1]

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, ttl: int) -> int:
        """Atomic increment (under the lock) returning the new count."""
        with self._lock:
            item = self._data.get(key)
            now = time.monotonic()
            n = int(item[1]) if item is not None and item[0] >= now else 0
            n += 1
            self._data[key] = (now + ttl, str(n))
            return n


class _RedisStore:
    def __init__(self, dsn: str) -> None:
        import redis

        self._r = redis.Redis.from_url(dsn, socket_timeout=3, socket_connect_timeout=3)

    def set(self, key: str, value: str, ttl: int) -> None:
        self._r.set(key, value, ex=ttl)

    def get(self, key: str) -> str | None:
        v = self._r.get(key)
        return v.decode() if isinstance(v, bytes) else v

    def delete(self, key: str) -> None:
        self._r.delete(key)

    def incr(self, key: str, ttl: int) -> int:
        """Server-side atomic INCR + expiry — concurrent guesses each get a
        distinct count, so the attempt cap can't be raced past."""
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        result = pipe.execute()
        return int(result[0])


_store = None


def _get_store():
    global _store
    if _store is None:
        dsn = settings.redis_dsn()
        _store = _RedisStore(dsn) if dsn else _MemoryStore()
    return _store


def issue_code(email: str) -> str:
    """Create (or replace) the pending code for this email and return it — the
    ONLY place the plaintext exists; the caller emails it and drops it."""
    code = f"{secrets.randbelow(10**6):06d}"
    salt = secrets.token_hex(8)
    # The record is immutable (salt + hash only) — it is never re-written on a
    # wrong guess, so its TTL is never re-armed and the code dies on schedule.
    # Attempts live in a SEPARATE atomic counter, not in this record.
    record = json.dumps({"salt": salt, "hash": _hash(salt, code)})
    store = _get_store()
    store.set(_PREFIX + email, record, settings.mfa_recovery_code_ttl_seconds)
    store.delete(_ATTEMPTS_PREFIX + email)  # clear any stale counter from a prior code
    return code


def verify_code(email: str, code: str) -> bool:
    """True exactly once per issued code. A wrong guess atomically counts an
    attempt; too many wrong guesses void the code so it must be re-requested."""
    store = _get_store()
    key = _PREFIX + email
    raw = store.get(key)
    if raw is None:
        return False
    record = json.loads(raw)
    if secrets.compare_digest(record["hash"], _hash(record["salt"], code)):
        store.delete(key)
        store.delete(_ATTEMPTS_PREFIX + email)
        return True
    # Atomic increment on a separate key: concurrent wrong guesses each get a
    # distinct count, so the cap cannot be raced past (the record read-modify-
    # write it replaced could). The counter shares the code's TTL budget.
    attempts = store.incr(_ATTEMPTS_PREFIX + email, settings.mfa_recovery_code_ttl_seconds)
    if attempts >= settings.mfa_recovery_max_attempts:
        store.delete(key)
        store.delete(_ATTEMPTS_PREFIX + email)
    return False
