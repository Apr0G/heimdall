"""The two hash-pinned lock files must agree on every package they share.

deid.lock is installed with PIP_USER=1 on top of the API image inside the
corpus-export task, and a user-site copy shadows the image's. A package pinned
here below requirements.lock therefore downgrades a task that holds
DATABASE_URL and the app role beneath the audited baseline — which is exactly
what happened with cryptography (48.0.1 vs 50.0.0) until 2026-08-29."""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
_PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==([^ \\]+)", re.M)


def _pins(name: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _PIN.finditer((BACKEND / name).read_text())}


def test_shared_pins_agree_between_requirements_and_deid_locks():
    req, deid = _pins("requirements.lock"), _pins("deid.lock")
    shared = sorted(set(req) & set(deid))
    assert shared, "deid.lock no longer shares packages with the image — revisit this test"
    drift = {n: (deid[n], req[n]) for n in shared if deid[n] != req[n]}
    assert not drift, f"deid.lock pins differ from requirements.lock: {drift}"
