"""Corrected-claim endpoints against a real Postgres: the happy path through
the in-place patcher (S3 stubbed with a synthetic claim PDF), the scanned-claim
refusal, and the download URL. All data synthetic (hard rule 1).
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Case, CorrectedClaim, Document, Practice, RiskReport, User
from app.services import s3
from app.tests.services.test_claim_patch import LINES, build_claim, service_lines

pytestmark = pytest.mark.asyncio

PROPOSED_EDITS = [
    {
        "kind": "add_modifier",
        "target": "20610",
        "instruction": "Add modifier 59/XS/XE to 20610 if distinct from 99213",
        "value": "59",
        "source": "ncci",
    },
    {
        "kind": "change_units",
        "target": "J3301",
        "instruction": "Reduce J3301 from 2 to ≤1 units/day",
        "value": "1",
        "source": "ncci",
    },
    {
        "kind": "documentation",
        "target": None,
        "instruction": "Document the separate E/M assessment",
        "value": None,
        "source": "model",
    },
]


async def _user(sessions) -> User:
    async with sessions() as s:
        practice = Practice(name="Practice A")
        s.add(practice)
        await s.flush()
        user = User(
            practice_id=practice.id,
            cognito_sub=f"sub-{uuid.uuid4()}",
            email=f"{uuid.uuid4()}@heimdall.test",
            role="doctor",
            is_active=True,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return user


async def _precheck_case(sessions, user: User, *, ocr_status: str) -> uuid.UUID:
    async with sessions() as s:
        case = Case(
            practice_id=user.practice_id,
            created_by=user.id,
            status="ready",
            case_type="pre_check",
            patient_initials="J.D.",
        )
        s.add(case)
        await s.flush()
        s.add(
            Document(
                case_id=case.id,
                doc_type="claim",
                s3_key=f"practices/{user.practice_id}/cases/{case.id}/claim/{uuid.uuid4()}.pdf",
                uploaded_by=user.id,
                ocr_status=ocr_status,
            )
        )
        s.add(
            Document(
                case_id=case.id,
                doc_type="clinical",
                s3_key=f"practices/{user.practice_id}/cases/{case.id}/clinical/{uuid.uuid4()}.pdf",
                uploaded_by=user.id,
                ocr_status="not_needed",
            )
        )
        s.add(
            RiskReport(
                case_id=case.id,
                overall_risk_band="high",
                findings=[],
                proposed_edits=PROPOSED_EDITS,
                deterministic_count=2,
                model_count=0,
            )
        )
        await s.commit()
        return case.id


def _client(sessions, user: User) -> AsyncClient:
    async def _override_user() -> User:
        return user

    async def _override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture(autouse=True)
async def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_s3(monkeypatch) -> dict:
    """S3 as a dict: the claim document reads back as a synthetic CMS-1500 and
    whatever the endpoint writes is captured for inspection."""
    store: dict[str, bytes] = {}
    claim_pdf = build_claim(LINES, style="cells")

    def get_bytes(key: str) -> bytes:
        return store.get(key, claim_pdf)

    def put_bytes(key: str, data: bytes, content_type: str) -> None:
        assert content_type == "application/pdf"
        store[key] = data

    monkeypatch.setattr(s3, "get_bytes", get_bytes)
    monkeypatch.setattr(s3, "put_bytes", put_bytes)
    monkeypatch.setattr("app.api.cases.presigned_get_url", lambda *a, **k: "https://s3/signed")
    return store


async def test_apply_selected_edits_produces_a_downloadable_corrected_claim(sessions, fake_s3):
    user = await _user(sessions)
    case_id = await _precheck_case(sessions, user, ocr_status="not_needed")

    async with _client(sessions, user) as client:
        detail = (await client.get(f"/api/cases/{case_id}")).json()
        assert detail["claim_editable"] is True
        assert detail["corrected_claim"] is None

        resp = await client.post(
            f"/api/cases/{case_id}/corrected-claim",
            json={"selections": [{"index": 0, "value": "XS"}, {"index": 1, "charge": "scale"}]},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["version"] == 1
        assert body["downloadable"] is True
        # J3301: 2 units at $45.00 → scaled to 1 unit = $22.50, total re-summed.
        assert body["total_updated"] is True
        assert [(r["index"], r["value"], r["applied"]) for r in body["results"]] == [
            (0, "XS", True),
            (1, "1", True),
        ]
        assert (
            body["results"][1]["charge_before_cents"],
            body["results"][1]["charge_after_cents"],
        ) == (
            4500,
            2250,
        )

        # The stored PDF is the doctor's claim with exactly those two changes.
        assert len(fake_s3) == 1
        ((key, pdf),) = fake_s3.items()
        assert key.startswith(f"practices/{user.practice_id}/cases/{case_id}/corrected-claim/")
        lines = service_lines(pdf)
        assert [(ln.cpt.text, [m.text for m in ln.modifiers], ln.units.text) for ln in lines] == [
            ("99213", ["25"], "1"),
            ("20610", ["XS"], "3"),
            ("J3301", ["RT"], "1"),
        ]

        detail = (await client.get(f"/api/cases/{case_id}")).json()
        assert detail["corrected_claim"]["version"] == 1

        resp = await client.get(f"/api/cases/{case_id}/corrected-claim/download-url")
        assert resp.status_code == 200
        assert resp.json() == {"url": "https://s3/signed"}

        # A second apply is a new version, never an overwrite.
        resp = await client.post(
            f"/api/cases/{case_id}/corrected-claim", json={"selections": [{"index": 1}]}
        )
        assert resp.status_code == 201
        assert resp.json()["version"] == 2

    async with sessions() as s:
        rows = (
            await s.scalars(
                select(CorrectedClaim)
                .where(CorrectedClaim.case_id == case_id)
                .order_by(CorrectedClaim.version)
            )
        ).all()
        assert [r.version for r in rows] == [1, 2]
        assert rows[0].downloaded_at is not None
        assert rows[0].created_by == user.id
        actions = (
            await s.scalars(
                select(AuditLog.action).where(AuditLog.resource_id == case_id).order_by(AuditLog.id)
            )
        ).all()
        assert actions.count("corrected_claim_create") == 2
        assert "corrected_claim_download" in actions


async def test_scanned_claim_is_refused_with_guidance(sessions, fake_s3):
    user = await _user(sessions)
    case_id = await _precheck_case(sessions, user, ocr_status="completed")
    async with _client(sessions, user) as client:
        detail = (await client.get(f"/api/cases/{case_id}")).json()
        assert detail["claim_editable"] is False
        resp = await client.post(
            f"/api/cases/{case_id}/corrected-claim", json={"selections": [{"index": 0}]}
        )
        assert resp.status_code == 409
        assert "scan" in resp.json()["detail"]
        assert fake_s3 == {}
        resp = await client.get(f"/api/cases/{case_id}/corrected-claim/download-url")
        assert resp.status_code == 404


async def test_documentation_edits_and_bad_indexes_are_422(sessions, fake_s3):
    user = await _user(sessions)
    case_id = await _precheck_case(sessions, user, ocr_status="not_needed")
    async with _client(sessions, user) as client:
        for selections in ([{"index": 2}], [{"index": 7}], [{"index": 0, "value": "5"}]):
            resp = await client.post(
                f"/api/cases/{case_id}/corrected-claim", json={"selections": selections}
            )
            assert resp.status_code == 422, selections
        assert fake_s3 == {}
