"""Keyed hashing for PHI-derived identifiers stored in the database.

A bare `sha256(member_id)` is not a de-identification control. Member IDs are
short, structured and payer-prefixed, so the keyspace is exhaustible offline:
anyone holding a database dump recovers the raw identifiers by enumeration.
HMAC with a secret pepper fixes that: the digest is not computable without the
key, and the key is not in the database, so a dump alone reveals nothing.

The pepper lives in Secrets Manager and arrives as `PHI_HASH_PEPPER`. Rotating it
breaks linkage between old and new values by design.

NOT used by the corpus export any more. Under Safe Harbor a code derived from
the individual's information must be removed (guidance §3.5), so the corpus
carries random record ids and the mapping lives in `corpus_records`
(models/corpus.py) — no hash of any identifier leaves the database.
"""

import hashlib
import hmac

from app.core.config import settings

# Domain separation: the same input under two different purposes must never
# produce the same digest. One purpose today; keep the parameter.
MEMBER_ID = "member_id"


class PepperMissingError(RuntimeError):
    """PHI_HASH_PEPPER is unset. Raised rather than silently falling back to an
    unkeyed digest, which would look identical in the database while providing
    none of the protection."""


def _pepper() -> bytes:
    pepper = settings.phi_hash_pepper.strip()
    if not pepper:
        raise PepperMissingError(
            "PHI_HASH_PEPPER is not set. Identifier hashing is a HIPAA control, so "
            "it fails closed rather than writing an offline-brute-forceable digest."
        )
    return pepper.encode("utf-8")


def keyed_hash(value: str, *, purpose: str, scope: str = "") -> str:
    """HMAC-SHA256 of `value`, domain-separated by `purpose` and optionally scoped.

    `scope` should be the practice id wherever the value is tenant-owned. Without
    it an identical hash appearing under two practices proves the same member is
    at both — a cross-tenant correlation the tenancy model otherwise forbids.
    """
    message = f"{purpose}|{scope}|{value.strip().lower()}".encode()
    return hmac.new(_pepper(), message, hashlib.sha256).hexdigest()


def is_configured() -> bool:
    """Whether a pepper is available, for callers that must degrade rather than
    fail (e.g. a script that can skip an optional field)."""
    return bool(settings.phi_hash_pepper.strip())
