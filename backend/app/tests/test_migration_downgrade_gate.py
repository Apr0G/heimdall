"""Every downgrade() that drops tenant data refuses without 0001's gate (LOW-20).

The migration modules are loaded from their files (they are not a package).
Calling downgrade() with the env var unset must raise before any `op` call, so
no database is needed — and the gate is the FIRST thing the function does.
"""

import importlib.util
from pathlib import Path

import pytest

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_GATED = [
    "0001_initial_schema.py",
    "0010_deactivation_requests.py",
    "0013_pre_check.py",
    "0016_corrected_claims.py",
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), _VERSIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", _GATED)
def test_downgrade_refuses_without_the_gate(name, monkeypatch):
    monkeypatch.delenv("ALEMBIC_ALLOW_INITIAL_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="DESTROY-ALL-DATA"):
        _load(name).downgrade()


@pytest.mark.parametrize("name", _GATED)
def test_gate_needs_the_exact_phrase(name, monkeypatch):
    monkeypatch.setenv("ALEMBIC_ALLOW_INITIAL_DOWNGRADE", "yes")
    with pytest.raises(RuntimeError):
        _load(name).downgrade()
