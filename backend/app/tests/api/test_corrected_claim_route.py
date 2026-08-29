"""HTTP translation of the corrected-claim service's failure modes (LOW-05,
LOW-11). The service is stubbed; the integration suite exercises it for real.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api import cases as cases_api
from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.services import corrected_claim as service

client = TestClient(app)


class _Session:
    def __init__(self, case):
        self.case = case
        self.committed = False

    async def get(self, model, pk):
        return self.case

    async def commit(self):
        self.committed = True

    async def refresh(self, row):
        pass

    async def scalars(self, stmt):
        return SimpleNamespace(all=lambda: [])


@pytest.fixture
def ctx(monkeypatch):
    user = MagicMock()
    user.id = uuid4()
    user.practice_id = uuid4()
    case = SimpleNamespace(
        id=uuid4(), practice_id=user.practice_id, case_type="pre_check", status="ready"
    )
    session = _Session(case)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: session
    monkeypatch.setattr(cases_api, "log_audit", AsyncMock())
    yield SimpleNamespace(user=user, case=case, session=session)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


def _post(case_id, body):
    return client.post(f"/api/cases/{case_id}/corrected-claim", json=body)


def test_version_conflict_is_409_and_nothing_commits(ctx, monkeypatch):
    async def _conflict(*a, **k):
        raise IntegrityError("INSERT corrected_claims", {}, Exception("duplicate key"))

    monkeypatch.setattr(service, "create_corrected_claim", _conflict)
    resp = _post(ctx.case.id, {"selections": [{"index": 0}]})
    assert resp.status_code == 409
    assert "Reload" in resp.json()["detail"]
    assert "duplicate" not in resp.text  # the driver message never reaches the client
    assert ctx.session.committed is False
    cases_api.log_audit.assert_not_awaited()


def test_stale_report_id_is_409_with_the_code_as_detail(ctx, monkeypatch):
    async def _stale(*a, **k):
        raise service.ClaimNotEditable("report_changed")

    monkeypatch.setattr(service, "create_corrected_claim", _stale)
    resp = _post(ctx.case.id, {"selections": [{"index": 0}], "risk_report_id": str(uuid4())})
    assert resp.status_code == 409
    # The client keys on the bare code to reload the report.
    assert resp.json()["detail"] == "report_changed"


def test_report_id_is_passed_through_to_the_service(ctx, monkeypatch):
    seen = {}
    report_id = uuid4()

    async def _capture(session, case, selections, user, *, risk_report_id=None):
        seen["risk_report_id"] = risk_report_id
        return SimpleNamespace(
            id=uuid4(),
            version=1,
            results=[],
            total_updated=None,
            s3_key=None,
            created_at=datetime.now(UTC),
            downloaded_at=None,
        )

    monkeypatch.setattr(service, "create_corrected_claim", _capture)
    resp = _post(ctx.case.id, {"selections": [{"index": 0}], "risk_report_id": str(report_id)})
    assert resp.status_code == 201, resp.text
    assert seen["risk_report_id"] == report_id

    # Omitting it stays valid for older clients: the service sees None.
    resp = _post(ctx.case.id, {"selections": [{"index": 0}]})
    assert resp.status_code == 201
    assert seen["risk_report_id"] is None


def test_malformed_report_id_is_422(ctx):
    resp = _post(ctx.case.id, {"selections": [{"index": 0}], "risk_report_id": "not-a-uuid"})
    assert resp.status_code == 422
