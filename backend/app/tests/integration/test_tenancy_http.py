"""Authenticated HTTP tests for the cross-tenant guards (HIGH-07).

Before this file the entire suite made four real HTTP requests, none of them
authenticated, and contained zero 404 assertions. That left the two controls whose
removal is a reportable breach provable only by reading the code:

  * `api/documents.py` — `case.practice_id != current_user.practice_id`. Delete
    that clause and GET /api/documents/{id}/download-url hands ANY authenticated
    user a working presigned S3 GET URL for another practice's denial letter or
    clinical notes. It is the single highest-value line in the repo: the one that
    mints a credential to PHI bytes.
  * `_get_owned_case` — the chokepoint for eight routes, with no test of its own.

Every assertion here is `== 404`, never `< 500` and never `in (403, 404)`. 404 is
the documented contract precisely so that case ids do not leak across practices;
a 403 would confirm the id exists and would be a real regression, so the test must
fail on it.

Needs a real PostgreSQL (TEST_DATABASE_URL); CI runs it against postgres:17.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from starlette.datastructures import Headers
from starlette.requests import Request

import app.core.auth as auth_module
from app.core.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import AppealLetter, Case, Document, Outcome, Practice, User

pytestmark = pytest.mark.asyncio


# Routes that take a case id from the path and must be tenant-scoped. (method,
# template, json body). Kept as data so a newly added case route is one line here.
CASE_ROUTES = [
    ("GET", "/api/cases/{case_id}", None),
    ("GET", "/api/cases/{case_id}/status", None),
    ("GET", "/api/cases/{case_id}/letter.pdf", None),
    ("POST", "/api/cases/{case_id}/mark-submitted", None),
    ("POST", "/api/cases/{case_id}/outcome", {"result": "overturned"}),
    ("POST", "/api/cases/{case_id}/retry", None),
    (
        "POST",
        "/api/cases/{case_id}/additional-upload-urls",
        {
            "documents": [
                {
                    "doc_type": "prior_auth",
                    "filename": "auth.pdf",
                    "content_type": "application/pdf",
                }
            ]
        },
    ),
    (
        "POST",
        "/api/cases/{case_id}/reanalyze",
        {
            "documents": [
                {
                    "doc_type": "prior_auth",
                    "s3_key": "tmp-uploads/x/y.pdf",
                    "filename": "a.pdf",
                }
            ]
        },
    ),
]


async def _make_tenant(sessions, name: str) -> User:
    async with sessions() as s:
        practice = Practice(name=name)
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


@pytest_asyncio.fixture
async def owner(sessions) -> User:
    """A user in practice A, which owns the fixture case."""
    return await _make_tenant(sessions, "Practice A")


@pytest_asyncio.fixture
async def outsider(sessions) -> User:
    """A user in a DIFFERENT practice. Fully legitimate, fully authenticated —
    just not entitled to practice A's rows."""
    return await _make_tenant(sessions, "Practice B")


@pytest_asyncio.fixture
async def owned_case(sessions, owner: User) -> dict:
    """A case in practice A with a document and a downloadable letter."""
    async with sessions() as s:
        case = Case(
            practice_id=owner.practice_id,
            created_by=owner.id,
            status="ready",
            payer_name="Test Payer",
            claim_number="CLM-TEST-0001",
            patient_initials="J.D.",
        )
        s.add(case)
        await s.flush()
        document = Document(
            case_id=case.id,
            doc_type="denial",
            s3_key=f"practices/{owner.practice_id}/cases/{case.id}/denial/{uuid.uuid4()}.pdf",
            uploaded_by=owner.id,
        )
        letter = AppealLetter(
            case_id=case.id,
            version=1,
            body="Full appeal letter body." * 40,
            status="draft",
        )
        s.add_all([document, letter])
        await s.commit()
        return {"case_id": case.id, "document_id": document.id}


def _client(sessions, user: User) -> AsyncClient:
    """An HTTP client authenticated as `user`.

    get_current_user is overridden rather than minting a real Cognito token: the
    token path is covered by test_jwt_verification.py, and what THIS file exercises
    is what the routes do once a caller is authenticated.
    """

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


@pytest.fixture(autouse=True)
def _no_aws(monkeypatch):
    """Stub the S3 calls so a positive-control request never touches AWS. The
    cross-tenant cases never reach these — the guard fires first, which is itself
    part of what is being asserted."""
    monkeypatch.setattr("app.services.s3.presigned_get_url", lambda *a, **k: "https://s3/signed")
    monkeypatch.setattr("app.services.s3.presigned_put_url", lambda *a, **k: "https://s3/signed")
    monkeypatch.setattr("app.api.documents.presigned_get_url", lambda *a, **k: "https://s3/signed")
    monkeypatch.setattr("app.api.cases.presigned_put_url", lambda *a, **k: "https://s3/signed")


# --- the guards --------------------------------------------------------------


@pytest.mark.parametrize(("method", "template", "body"), CASE_ROUTES)
async def test_case_routes_are_404_for_another_practice(
    sessions, outsider, owned_case, method, template, body
):
    """Exactly 404 — not 403, which would confirm the id exists."""
    url = template.format(case_id=owned_case["case_id"])
    async with _client(sessions, outsider) as client:
        resp = await client.request(method, url, json=body)
    assert resp.status_code == 404, f"{method} {template} leaked: {resp.status_code}"


async def test_document_download_url_is_404_for_another_practice(sessions, outsider, owned_case):
    """The highest-value guard in the repo: this route mints a presigned S3 GET
    URL to raw PHI bytes. A regression here is a cross-practice PHI disclosure."""
    async with _client(sessions, outsider) as client:
        resp = await client.get(f"/api/documents/{owned_case['document_id']}/download-url")
    assert resp.status_code == 404
    assert "url" not in resp.json()


async def test_document_download_url_works_for_the_owner(sessions, owner, owned_case):
    """Positive control. Without it, a guard that 404s EVERYTHING would pass every
    test above while breaking the product."""
    async with _client(sessions, owner) as client:
        resp = await client.get(f"/api/documents/{owned_case['document_id']}/download-url")
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://")


async def test_case_detail_works_for_the_owner(sessions, owner, owned_case):
    async with _client(sessions, owner) as client:
        resp = await client.get(f"/api/cases/{owned_case['case_id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(owned_case["case_id"])


async def test_unknown_ids_are_404_not_500(sessions, owner):
    """A random UUID must 404 cleanly rather than raising."""
    missing = uuid.uuid4()
    async with _client(sessions, owner) as client:
        assert (await client.get(f"/api/cases/{missing}")).status_code == 404
        assert (await client.get(f"/api/documents/{missing}/download-url")).status_code == 404


# --- list/summary endpoints must not aggregate across practices ---------------


async def test_case_list_excludes_other_practices(sessions, outsider, owned_case):
    async with _client(sessions, outsider) as client:
        resp = await client.get("/api/cases")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert all(item["id"] != str(owned_case["case_id"]) for item in body["items"])


async def test_summary_excludes_other_practices_outcomes(sessions, owner, outsider, owned_case):
    """`/summary` aggregates money. A missing tenant filter here would report
    another practice's recoveries as this practice's."""
    async with sessions() as s:
        case = await s.get(Case, owned_case["case_id"])
        case.status = "resolved"
        case.denied_amount_cents = 45000
        s.add(
            Outcome(
                case_id=case.id,
                result="overturned",
                action_taken="appealed",
                amount_recovered_cents=45000,
                source="user_reported",
                reported_by=owner.id,
            )
        )
        await s.commit()

    async with _client(sessions, outsider) as client:
        resp = await client.get("/api/cases/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_recovered_cents"] == 0
    assert body["resolved_count"] == 0
    assert body["win_count"] == 0

    async with _client(sessions, owner) as client:
        owner_body = (await client.get("/api/cases/summary")).json()
    assert owner_body["total_recovered_cents"] == 45000


async def test_processing_ids_excludes_other_practices(sessions, owner, outsider, owned_case):
    async with sessions() as s:
        case = await s.get(Case, owned_case["case_id"])
        case.status = "processing"
        await s.commit()

    async with _client(sessions, outsider) as client:
        ids = (await client.get("/api/cases/processing-ids")).json()["ids"]
    assert str(owned_case["case_id"]) not in ids

    async with _client(sessions, owner) as client:
        ids = (await client.get("/api/cases/processing-ids")).json()["ids"]
    assert str(owned_case["case_id"]) in ids


# --- the kill switch (MED-10) ------------------------------------------------


async def test_deactivated_user_is_rejected(sessions, owner, owned_case):
    """Cognito access tokens cannot be revoked, so this column is the only lever
    an admin has against a compromised session."""
    from app.core.auth import get_current_user as real_get_current_user

    async with sessions() as s:
        user = await s.get(User, owner.id)
        user.is_active = False
        await s.commit()

    # Exercise the REAL dependency here — overriding it would skip the check.
    app.dependency_overrides.clear()

    async def _override_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db

    async def _fake_verify(token: str) -> dict:
        return {"sub": owner.cognito_sub, "token_use": "access"}

    original = auth_module.verify_access_token
    auth_module.verify_access_token = _fake_verify
    try:
        assert real_get_current_user is not None
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.cookies.set("hd_session", "any-token")
            resp = await client.get(f"/api/cases/{owned_case['case_id']}")
        assert resp.status_code == 401
    finally:
        auth_module.verify_access_token = original


# --- letter lifecycle (LOW-12, LOW-24) ---------------------------------------
#
# `status`, `finalized_at` and `downloaded_at` were declared in 0001 and written
# by nothing, so three letter_status members were unreachable and
# export_corpus's "prefer the finalized letter" branch had never executed.


async def test_download_marks_the_letter_downloaded(sessions, owner, owned_case, monkeypatch):
    monkeypatch.setattr("app.services.pdf_gen.render_letter_pdf", lambda body: b"%PDF-1.4 fake")
    async with _client(sessions, owner) as client:
        resp = await client.get(f"/api/cases/{owned_case['case_id']}/letter.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment;")

    async with sessions() as s:
        letter = await s.scalar(
            select(AppealLetter).where(AppealLetter.case_id == owned_case["case_id"])
        )
    assert letter.status == "downloaded"
    assert letter.downloaded_at is not None


async def test_mark_submitted_finalizes_the_letter(sessions, owner, owned_case):
    async with _client(sessions, owner) as client:
        resp = await client.post(f"/api/cases/{owned_case['case_id']}/mark-submitted")
    assert resp.status_code == 200

    async with sessions() as s:
        letter = await s.scalar(
            select(AppealLetter).where(AppealLetter.case_id == owned_case["case_id"])
        )
    assert letter.status == "finalized"
    assert letter.finalized_at is not None


async def test_archived_letter_cannot_be_downloaded(sessions, owner, owned_case, monkeypatch):
    """A re-analysis that retracts appealability archives the draft. The practice
    must not be able to mail an appeal the system has since withdrawn."""
    monkeypatch.setattr("app.services.pdf_gen.render_letter_pdf", lambda body: b"%PDF-1.4 fake")
    async with sessions() as s:
        letter = await s.scalar(
            select(AppealLetter).where(AppealLetter.case_id == owned_case["case_id"])
        )
        letter.status = "archived"
        await s.commit()

    async with _client(sessions, owner) as client:
        resp = await client.get(f"/api/cases/{owned_case['case_id']}/letter.pdf")
    assert resp.status_code == 409


async def test_content_disposition_survives_non_latin1_initials(
    sessions, owner, owned_case, monkeypatch
):
    """U+2019 in "O’Brien" is not encodable as latin-1, and Starlette encodes
    header values as latin-1 — so this used to raise UnicodeEncodeError and 500
    the download permanently, with no UI path to fix the stored value."""
    monkeypatch.setattr("app.services.pdf_gen.render_letter_pdf", lambda body: b"%PDF-1.4 fake")
    async with sessions() as s:
        case = await s.get(Case, owned_case["case_id"])
        case.patient_initials = "O’B"
        await s.commit()

    async with _client(sessions, owner) as client:
        resp = await client.get(f"/api/cases/{owned_case['case_id']}/letter.pdf")
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    disposition.encode("latin-1")  # must not raise
    assert "filename*=UTF-8''" in disposition


# --- MED-20: the outcome upsert must not race its unique constraint ----------


async def test_concurrent_outcome_posts_do_not_500(sessions, owner, owned_case):
    """A double-clicked submit had both requests see no existing row, both
    insert, and the loser raise IntegrityError at commit -> unhandled 500."""
    async with _client(sessions, owner) as client:
        await client.post(f"/api/cases/{owned_case['case_id']}/mark-submitted")
        first = await client.post(
            f"/api/cases/{owned_case['case_id']}/outcome",
            json={"result": "overturned", "amount_recovered_cents": 45000},
        )
        second = await client.post(
            f"/api/cases/{owned_case['case_id']}/outcome",
            json={"result": "upheld", "amount_recovered_cents": 0},
        )
    assert first.status_code == 200
    assert second.status_code == 200  # upsert, not a constraint violation

    async with sessions() as s:
        rows = (
            await s.scalars(select(Outcome).where(Outcome.case_id == owned_case["case_id"]))
        ).all()
    assert len(rows) == 1
    assert rows[0].result == "upheld"  # last write wins


# --- MED-21: bad enum input is a 422, not a 500 ------------------------------


async def test_invalid_outcome_result_is_422_not_500(sessions, owner, owned_case):
    async with _client(sessions, owner) as client:
        await client.post(f"/api/cases/{owned_case['case_id']}/mark-submitted")
        resp = await client.post(
            f"/api/cases/{owned_case['case_id']}/outcome", json={"result": "Overturned"}
        )
    assert resp.status_code == 422


async def test_invalid_action_taken_is_422_not_500(sessions, owner, owned_case):
    """`action_taken` was a bare `str` that nothing checked, so "escalated"
    reached the native enum and 500'd at commit — rolling back the audit row
    written moments earlier, so the failed attempt left no trace."""
    async with _client(sessions, owner) as client:
        await client.post(f"/api/cases/{owned_case['case_id']}/mark-submitted")
        resp = await client.post(
            f"/api/cases/{owned_case['case_id']}/outcome",
            json={"result": "overturned", "action_taken": "escalated"},
        )
    assert resp.status_code == 422


async def test_invalid_status_filter_is_422_not_500(sessions, owner):
    """`?status=Ready` reached a native Postgres enum and raised DataError."""
    async with _client(sessions, owner) as client:
        assert (await client.get("/api/cases?status=Ready")).status_code == 422
        assert (await client.get("/api/cases?status=ready")).status_code == 200


# --- MED-11 second pass: an OPEN tab must still time out ----------------------
#
# The frontend polls processing-ids every 12s in the background. Before this,
# those polls stamped last_seen_at, so leaving the app open on screen held the
# session alive forever — the product's own traffic defeating the control.


def _auth_client(sessions, user):
    """A client that exercises the REAL get_current_user, so the idle check runs."""

    async def _override_db():
        async with sessions() as s:
            yield s

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _override_db

    async def _fake_verify(token: str) -> dict:
        return {"sub": user.cognito_sub, "token_use": "access"}

    auth_module.verify_access_token = _fake_verify
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    c.cookies.set("hd_session", "any-token")
    return c


async def _set_last_seen(sessions, user_id, when):
    async with sessions() as s:
        u = await s.get(User, user_id)
        u.last_seen_at = when
        await s.commit()


async def test_polling_does_not_advance_the_idle_clock(sessions, owner, owned_case):
    """THE test. A session that is idle but not yet expired, polled by a tab
    sitting open on someone's desk, must NOT have its clock refreshed.

    Note what this deliberately does NOT assert: that an already-expired session
    gets 401. That is true whether or not polls count as activity — the timeout
    is evaluated before the stamp — so asserting it proves nothing about the bug.
    The regression is silent, and only visible in `last_seen_at` afterwards.
    """
    original = auth_module.verify_access_token
    try:
        stale = datetime.now(UTC) - timedelta(minutes=10)  # idle, still valid
        await _set_last_seen(sessions, owner.id, stale)

        async with _auth_client(sessions, owner) as client:
            for _ in range(3):  # as the tab would, every 12s
                resp = await client.get("/api/cases/processing-ids")
                assert resp.status_code == 200

        async with sessions() as s:
            u = await s.get(User, owner.id)
        drift = abs((u.last_seen_at - stale).total_seconds())
        assert drift < 1, (
            "polling refreshed last_seen_at — an open tab would keep the session "
            f"alive indefinitely (clock moved {drift:.0f}s)"
        )
    finally:
        auth_module.verify_access_token = original


async def test_real_requests_do_advance_the_idle_clock(sessions, owner, owned_case):
    """Positive control. Without it, a change that stopped stamping on EVERY
    path would pass the test above while logging active users out."""
    original = auth_module.verify_access_token
    try:
        stale = datetime.now(UTC) - timedelta(minutes=10)
        await _set_last_seen(sessions, owner.id, stale)

        async with _auth_client(sessions, owner) as client:
            resp = await client.get(f"/api/cases/{owned_case['case_id']}")
            assert resp.status_code == 200

        async with sessions() as s:
            u = await s.get(User, owner.id)
        assert u.last_seen_at > stale, "opening a case should count as activity"
    finally:
        auth_module.verify_access_token = original


async def test_heartbeat_keeps_a_live_session_alive(sessions, owner):
    """Someone reading without clicking stays signed in."""
    original = auth_module.verify_access_token
    try:
        stale = datetime.now(UTC) - timedelta(minutes=10)  # idle, but not expired
        await _set_last_seen(sessions, owner.id, stale)
        async with _auth_client(sessions, owner) as client:
            resp = await client.post("/api/auth/heartbeat")
        assert resp.status_code == 204

        async with sessions() as s:
            u = await s.get(User, owner.id)
        assert u.last_seen_at > stale  # clock refreshed
    finally:
        auth_module.verify_access_token = original


async def test_heartbeat_cannot_revive_an_already_expired_session(sessions, owner):
    """The timeout is evaluated BEFORE the stamp, so a stale session cannot
    heartbeat its way back to life."""
    original = auth_module.verify_access_token
    try:
        await _set_last_seen(sessions, owner.id, datetime.now(UTC) - timedelta(minutes=45))
        async with _auth_client(sessions, owner) as client:
            resp = await client.post("/api/auth/heartbeat")
        assert resp.status_code == 401
    finally:
        auth_module.verify_access_token = original


# --- login must reset the idle clock -----------------------------------------


async def test_login_resets_the_idle_clock(sessions, owner):
    """A brand-new session must NOT inherit the previous session's staleness.

    This shipped broken on 2026-07-30 and locked everyone out of production:
    /api/auth/login and /api/auth/mfa/verify both returned 200, then the very
    next request 401'd — because `_finalize_login` never touched `last_seen_at`.
    By the time someone comes back to log in they have almost always been idle
    longer than the timeout, so the fresh session was expired before its first
    request. The failure is invisible in the login response itself, which is why
    the logs showed "200, 200, 401".
    """
    import app.api.auth as auth_api
    from app.api.auth import _finalize_login

    ancient = datetime.now(UTC) - timedelta(days=2)
    await _set_last_seen(sessions, owner.id, ancient)

    class _Resp:
        def set_cookie(self, **kw):
            pass

    async def _fake_verify(token: str) -> dict:
        return {"sub": owner.cognito_sub, "token_use": "access"}

    original = auth_api.verify_access_token
    auth_api.verify_access_token = _fake_verify
    try:
        req = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/auth/login",
                "headers": Headers({}).raw,
                "client": ("203.0.113.9", 1234),
                "query_string": b"",
            }
        )
        async with sessions() as s:
            await _finalize_login(
                s, req, _Resp(), {"AccessToken": "t", "ExpiresIn": 3600}, owner.email
            )

        async with sessions() as s:
            u = await s.get(User, owner.id)
        assert u.last_seen_at > ancient, "login did not reset the idle clock"
        assert (datetime.now(UTC) - u.last_seen_at) < timedelta(minutes=1)
    finally:
        auth_api.verify_access_token = original


# --- app-side session revocation (audit 2026-08-21 MED-31) -------------------
#
# The predicate is unit-tested in core/test_session_revocation.py; this proves
# get_current_user actually ENFORCES it, with the one-session-kept carve-out.


def _revocation_client(sessions, user, *, iat: int, jti: str):
    async def _override_db():
        async with sessions() as s:
            yield s

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _override_db

    async def _fake_verify(token: str) -> dict:
        return {"sub": user.cognito_sub, "token_use": "access", "iat": iat, "jti": jti}

    auth_module.verify_access_token = _fake_verify
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    c.cookies.set("hd_session", "any-token")
    return c


async def test_revoked_sessions_are_rejected_except_the_kept_one(sessions, owner, owned_case):
    original = auth_module.verify_access_token
    old_iat = int((datetime.now(UTC) - timedelta(minutes=10)).timestamp())
    try:
        async with sessions() as s:
            u = await s.get(User, owner.id)
            u.sessions_revoked_at = datetime.now(UTC) - timedelta(minutes=5)
            u.session_keep_jti = "the-one-that-changed-the-password"
            await s.commit()

        # An old token with a different jti: revoked.
        async with _revocation_client(sessions, owner, iat=old_iat, jti="stolen") as c:
            assert (await c.get(f"/api/cases/{owned_case['case_id']}")).status_code == 401
        # The same-age token that performed the change: kept.
        async with _revocation_client(
            sessions, owner, iat=old_iat, jti="the-one-that-changed-the-password"
        ) as c:
            assert (await c.get(f"/api/cases/{owned_case['case_id']}")).status_code == 200
        # A token issued after the revocation: fine.
        now_iat = int(datetime.now(UTC).timestamp()) + 1
        async with _revocation_client(sessions, owner, iat=now_iat, jti="fresh") as c:
            assert (await c.get(f"/api/cases/{owned_case['case_id']}")).status_code == 200
    finally:
        auth_module.verify_access_token = original
        app.dependency_overrides.clear()


# --- upload-key prefix guard (audit 2026-08-21 MED-32) ------------------------
#
# The temp key a caller submits must sit under THEIR practice prefix; otherwise
# a leaked temp key would let one practice attach another's uploaded PDF.


async def test_create_case_refuses_another_practices_upload_key(
    sessions, owner, outsider, monkeypatch
):
    moved: list = []
    monkeypatch.setattr("app.api.cases.move_object", lambda src, dst: moved.append((src, dst)))
    monkeypatch.setattr("app.api.cases.head_object", lambda key: {"ContentLength": 10})
    body = {
        "documents": [
            {
                "doc_type": t,
                "s3_key": f"tmp-uploads/{owner.practice_id}/{uuid.uuid4()}.pdf",
                "filename": f"{t}.pdf",
            }
            for t in ("denial", "claim", "clinical")
        ]
    }
    async with _client(sessions, outsider) as client:
        resp = await client.post("/api/cases", json=body)
    assert resp.status_code == 400, resp.text
    assert moved == []
    async with sessions() as s:
        assert (
            await s.scalar(select(Document).where(Document.s3_key.like(f"%{owner.practice_id}%")))
        ) is None


# --- audit_logs append-only at the grant level (audit 2026-08-21 MED-34) ------


async def test_app_role_cannot_update_delete_or_truncate_audit_logs(sessions):
    from sqlalchemy import text

    async with sessions() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'heimdall_app' AND table_name = 'audit_logs'"
                )
            )
        ).scalars()
        assert set(rows) == {"INSERT", "SELECT"}
        enabled = (
            await s.execute(
                text("SELECT tgenabled FROM pg_trigger WHERE tgname LIKE 'trg_audit_logs_no_%'")
            )
        ).scalars()
        assert {e.decode() if isinstance(e, bytes) else e for e in enabled} == {"A"}  # ALWAYS
