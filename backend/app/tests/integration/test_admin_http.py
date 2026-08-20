"""Authenticated HTTP tests for GET /api/admin/overview.

This route is the deliberate exception to Hard rule 3 (no global view), so the
tests prove the two properties that make the exception acceptable:

  * the role gate holds — doctor and office_manager get exactly 403 (this route
    is deliberately NOT the tenancy-404 pattern: its existence is no secret,
    only its data is privileged) and leave no audit row;
  * an admin's read is genuinely global (numbers from BOTH seeded practices,
    tokens attributed through the ModelRun→Case join) and is audit-logged.

The suite's database is shared across tests with no truncation, so global
totals are asserted with `>=` / membership; exact assertions are made only on
the per-practice breakdown rows this file seeds itself.

Needs a real PostgreSQL (TEST_DATABASE_URL); CI runs it against postgres:17.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Case, ModelRun, Outcome, Practice, User

pytestmark = pytest.mark.asyncio

CASE_STATUSES = {"draft", "processing", "ready", "submitted", "resolved", "error"}
RUN_PURPOSES = {"extraction", "analysis", "letter_draft", "classification"}
OUTCOME_RESULTS = {"overturned", "upheld", "partial", "pending", "withdrawn"}


async def _make_tenant(sessions, name: str, role: str) -> User:
    """Like test_tenancy_http's helper, but with the role as a parameter —
    the fixture there hardcodes 'doctor', and this file is about roles."""
    async with sessions() as s:
        practice = Practice(name=name)
        s.add(practice)
        await s.flush()
        user = User(
            practice_id=practice.id,
            cognito_sub=f"sub-{uuid.uuid4()}",
            email=f"{uuid.uuid4()}@heimdall.test",
            role=role,
            is_active=True,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return user


async def _seed_activity(
    sessions, owner: User, *, tokens: tuple[int, int], recovered_cents: int
) -> uuid.UUID:
    """One resolved case with a model run and a won outcome for `owner`'s
    practice. Synthetic PHI only (Hard rule 1)."""
    async with sessions() as s:
        case = Case(
            practice_id=owner.practice_id,
            created_by=owner.id,
            status="resolved",
            payer_name="Test Payer",
            claim_number="CLM-TEST-0001",
            patient_initials="J.D.",
            denied_amount_cents=recovered_cents,
        )
        s.add(case)
        await s.flush()
        s.add(
            ModelRun(
                case_id=case.id,
                purpose="extraction",
                model_id="us.anthropic.claude-sonnet-4-6",
                input_tokens=tokens[0],
                output_tokens=tokens[1],
                latency_ms=1200,
                status="success",
            )
        )
        s.add(
            Outcome(
                case_id=case.id,
                result="overturned",
                action_taken="appealed",
                amount_recovered_cents=recovered_cents,
                source="user_reported",
                reported_by=owner.id,
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


async def _audit_rows_for(sessions, user_id) -> list[AuditLog]:
    async with sessions() as s:
        return (
            await s.scalars(
                select(AuditLog).where(
                    AuditLog.action == "admin_overview_view", AuditLog.user_id == user_id
                )
            )
        ).all()


# --- the role gate ------------------------------------------------------------


@pytest.mark.parametrize("role", ["doctor", "office_manager"])
async def test_non_admin_roles_get_403_and_no_audit_row(sessions, role):
    user = await _make_tenant(sessions, f"Gate {role}", role)
    async with _client(sessions, user) as client:
        resp = await client.get("/api/admin/overview")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Insufficient permissions"
    # The 403 fires in the dependency, before the handler body — nothing to audit.
    assert await _audit_rows_for(sessions, user.id) == []


# --- the global read ----------------------------------------------------------


async def test_admin_sees_both_practices_with_correct_attribution(sessions):
    admin = await _make_tenant(sessions, "Admin HQ", "admin")
    doc_a = await _make_tenant(sessions, "Practice Alpha", "doctor")
    doc_b = await _make_tenant(sessions, "Practice Beta", "doctor")
    await _seed_activity(sessions, doc_a, tokens=(1_000_000, 200_000), recovered_cents=45_000)
    await _seed_activity(sessions, doc_b, tokens=(500_000, 100_000), recovered_cents=30_000)

    async with _client(sessions, admin) as client:
        resp = await client.get("/api/admin/overview")
    assert resp.status_code == 200
    body = resp.json()

    # Global rollups: >= because the suite's database is shared across tests.
    assert body["practice_count"] >= 3
    assert body["cases"]["total"] >= 2
    assert body["users"]["total"] >= 3
    assert body["users"]["by_role"]["admin"] >= 1
    assert body["outcomes"]["amount_recovered_cents"] >= 75_000
    assert body["outcomes"]["by_result"]["overturned"] >= 2
    assert body["model_runs"]["input_tokens"] >= 1_500_000
    assert isinstance(body["model_runs"]["estimated_cost_cents"], int)

    by_id = {p["id"]: p for p in body["practices"]}
    row_a = by_id[str(doc_a.practice_id)]
    row_b = by_id[str(doc_b.practice_id)]

    # Exact per-practice attribution — proves the ModelRun→Case join groups by
    # the right tenant and nothing bleeds between practices.
    assert row_a["case_count"] == 1
    assert row_a["cases_by_status"]["resolved"] == 1
    assert row_a["input_tokens"] == 1_000_000
    assert row_a["output_tokens"] == 200_000
    # (1_000_000*300 + 200_000*1500) // 1_000_000 = 600 cents.
    assert row_a["estimated_cost_cents"] == 600
    assert row_a["amount_recovered_cents"] == 45_000
    assert row_a["last_activity_at"] is not None

    assert row_b["input_tokens"] == 500_000
    assert row_b["output_tokens"] == 100_000
    assert row_b["amount_recovered_cents"] == 30_000

    # Aggregates only — the response must never carry case-level PHI fields.
    assert "patient_initials" not in resp.text
    assert "claim_number" not in resp.text
    assert "CLM-TEST" not in resp.text


async def test_admin_view_writes_an_audit_row(sessions):
    admin = await _make_tenant(sessions, "Audit HQ", "admin")
    async with _client(sessions, admin) as client:
        assert (await client.get("/api/admin/overview")).status_code == 200
    rows = await _audit_rows_for(sessions, admin.id)
    assert len(rows) == 1
    assert rows[0].resource_type == "admin_overview"
    assert rows[0].practice_id == admin.practice_id


async def test_enum_maps_are_zero_filled_and_empty_practices_read_as_zero(sessions):
    """A practice with no cases must appear with explicit zeros, and every enum
    member must be a key — the frontend renders these dicts without key-checks."""
    admin = await _make_tenant(sessions, "Empty Practice HQ", "admin")

    async with _client(sessions, admin) as client:
        body = (await client.get("/api/admin/overview")).json()

    assert set(body["cases"]["by_status"]) == CASE_STATUSES
    assert set(body["model_runs"]["by_purpose"]) == RUN_PURPOSES
    assert set(body["outcomes"]["by_result"]) == OUTCOME_RESULTS

    row = {p["id"]: p for p in body["practices"]}[str(admin.practice_id)]
    assert row["case_count"] == 0
    assert set(row["cases_by_status"]) == CASE_STATUSES
    assert row["input_tokens"] == 0
    assert row["estimated_cost_cents"] == 0
    assert row["amount_recovered_cents"] == 0
    assert row["user_count"] == 1  # the admin themselves
