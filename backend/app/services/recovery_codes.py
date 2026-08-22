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
    record = json.dumps({"salt": salt, "hash": _hash(salt, code), "attempts": 0})
    _get_store().set(_PREFIX + email, record, settings.mfa_recovery_code_ttl_seconds)
    return code


def verify_code(email: str, code: str) -> bool:
    """True exactly once per issued code. A wrong guess counts an attempt; too many
    wrong guesses void the code so it must be re-requested."""
    store = _get_store()
    key = _PREFIX + email
    raw = store.get(key)
    if raw is None:
        return False
    record = json.loads(raw)
    if secrets.compare_digest(record["hash"], _hash(record["salt"], code)):
        store.delete(key)
        return True
    record["attempts"] += 1
    if record["attempts"] >= settings.mfa_recovery_max_attempts:
        store.delete(key)
    else:
        # Keep the original expiry budget roughly intact rather than extending it.
        store.set(key, json.dumps(record), settings.mfa_recovery_code_ttl_seconds)
    return False
