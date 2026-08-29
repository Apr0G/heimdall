"""The fail-closed AI limiter on the real model-invoking routes. It is the only
bound on Bedrock/Textract spend and on CPU-heavy claim patching; the login
throttle has this test, the AI limiter did not (audit 2026-08-28 MED-17)."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app

client = TestClient(app, raise_server_exceptions=False)

AI_ROUTES = [
    (
        "/api/cases",
        {"documents": [{"doc_type": "denial", "s3_key": "tmp-uploads/x", "filename": "a.pdf"}]},
    ),
    (f"/api/cases/{uuid.uuid4()}/retry", None),
    (f"/api/cases/{uuid.uuid4()}/reanalyze", {"documents": []}),
    (f"/api/cases/{uuid.uuid4()}/corrected-claim", {"selections": [{"index": 0}]}),
]


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.practice_id = uuid.uuid4()
    u.role = "doctor"
    u.is_active = True
    return u


class _NeverTouched:
    """A session any query would blow up on — the limiter must answer first."""

    def __getattr__(self, name):  # pragma: no cover - only hit on regression
        raise AssertionError(f"route body ran: session.{name}")


@pytest.fixture(autouse=True)
def _auth():
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = lambda: _NeverTouched()
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


def test_every_model_invoking_route_carries_the_ai_limiter():
    limited = {name.rsplit(".", 1)[-1] for name in rate_limit.ai_limiter._route_limits}
    assert {"create_case", "retry_case", "reanalyze_case", "create_corrected_claim"} <= limited


def test_ai_limiter_fails_closed_and_the_general_limiter_open():
    assert rate_limit.ai_limiter._swallow_errors is False
    assert rate_limit.limiter._swallow_errors is True


@pytest.mark.parametrize("path,body", AI_ROUTES)
def test_exhausted_limit_is_429_before_the_route_body(monkeypatch, path, body):
    exhausted = MagicMock()
    exhausted.hit.return_value = False
    exhausted.get_window_stats.return_value = (0, 0)
    monkeypatch.setattr(rate_limit.ai_limiter, "_limiter", exhausted)
    resp = client.post(path, json=body)
    assert resp.status_code == 429, resp.text
    assert exhausted.hit.called


@pytest.mark.parametrize("path,body", AI_ROUTES)
def test_storage_error_is_a_5xx_not_a_free_call(monkeypatch, path, body):
    broken = MagicMock()
    broken.hit.side_effect = ConnectionError("redis down")
    monkeypatch.setattr(rate_limit.ai_limiter, "_limiter", broken)
    resp = client.post(path, json=body)
    assert resp.status_code >= 500, resp.text
