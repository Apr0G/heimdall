"""One case runs one pipeline — verified against a real PostgreSQL.

These cover what the unit tests structurally cannot: the `now() - INTERVAL` bind,
real row-lock contention between two connections, and the `updated_at` trigger
that stall detection depends on.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import or_, select, text, update

from app.api.cases import STALE_PROCESSING, _claim_for_pipeline, _stalled_sql
from app.models import Case


async def _make_case(
    sessions, user, status: str, updated_ago: timedelta | None = None
) -> uuid.UUID:
    async with sessions() as s:
        case = Case(practice_id=user.practice_id, created_by=user.id, status=status)
        s.add(case)
        await s.commit()
        case_id = case.id
    if updated_ago is not None:
        # set_updated_at() stamps NEW.updated_at = now() on EVERY update, so a
        # plain `SET updated_at = <past>` is silently overwritten by the trigger.
        # The trigger has to be suspended to age a row — the same applies to
        # simulating a stalled case by hand in any environment.
        async with sessions() as s:
            await s.execute(text("ALTER TABLE cases DISABLE TRIGGER trg_cases_set_updated_at"))
            await s.execute(
                text("UPDATE cases SET updated_at = :ts WHERE id = :id"),
                {"ts": datetime.now(UTC) - updated_ago, "id": case_id},
            )
            await s.execute(text("ALTER TABLE cases ENABLE TRIGGER trg_cases_set_updated_at"))
            await s.commit()
    return case_id


async def _claim(sessions, case_id, user, when, conflict="conflict"):
    """Claim in its own connection and commit, so a competing claim really has to
    wait on the row lock. Returns the run token, or the HTTPException raised."""
    async with sessions() as s:
        try:
            run_id = await _claim_for_pipeline(s, case_id, user, when=when, conflict=conflict)
            await s.commit()
            return run_id
        except HTTPException as exc:
            await s.rollback()
            return exc


_RETRYABLE = or_(Case.status == "error", _stalled_sql())


async def test_updated_at_trigger_fires(sessions, tenant):
    """Stall detection is built entirely on this trigger; if it stops firing, a
    dead pipeline never becomes retryable."""
    case_id = await _make_case(sessions, tenant, "processing")
    async with sessions() as s:
        before = await s.scalar(select(Case.updated_at).where(Case.id == case_id))
    await asyncio.sleep(0.01)
    async with sessions() as s:
        await s.execute(update(Case).where(Case.id == case_id).values(status="error"))
        await s.commit()
    async with sessions() as s:
        after = await s.scalar(select(Case.updated_at).where(Case.id == case_id))
    assert after > before, "set_updated_at trigger did not fire on UPDATE"


async def test_stalled_sql_matches_a_backdated_case(sessions, tenant):
    """Executes `now() - INTERVAL` with a Python timedelta bound as a parameter —
    the path that compiled but had never actually run against a database."""
    case_id = await _make_case(
        sessions, tenant, "processing", updated_ago=STALE_PROCESSING + timedelta(minutes=1)
    )
    async with sessions() as s:
        found = await s.scalar(select(Case.id).where(Case.id == case_id, _stalled_sql()))
    assert found == case_id


async def test_stalled_sql_ignores_a_fresh_processing_case(sessions, tenant):
    case_id = await _make_case(sessions, tenant, "processing")
    async with sessions() as s:
        found = await s.scalar(select(Case.id).where(Case.id == case_id, _stalled_sql()))
    assert found is None, "a case that just started must not read as stalled"


async def test_concurrent_claims_exactly_one_wins(sessions, tenant):
    """The guarantee the whole fix rests on. Two claims race for one case; the
    loser must block on the row lock, re-evaluate, and be rejected."""
    case_id = await _make_case(sessions, tenant, "error")

    results = await asyncio.gather(
        _claim(sessions, case_id, tenant, _RETRYABLE),
        _claim(sessions, case_id, tenant, _RETRYABLE),
    )

    winners = [r for r in results if isinstance(r, uuid.UUID)]
    losers = [r for r in results if isinstance(r, HTTPException)]
    assert len(winners) == 1, f"expected exactly one winner, got {results}"
    assert len(losers) == 1 and losers[0].status_code == 409

    # The surviving token is the winner's — the loser wrote nothing.
    async with sessions() as s:
        stored = await s.scalar(select(Case.pipeline_run_id).where(Case.id == case_id))
    assert stored == winners[0]


async def test_read_then_write_would_let_both_through(sessions, tenant):
    """Proof these tests have teeth: the pattern this fix replaced, reproduced
    here, produces TWO winners on the same case. If someone 'simplifies'
    _claim_for_pipeline back to read-then-write, the test above starts failing."""
    case_id = await _make_case(sessions, tenant, "error")

    async def legacy_claim():
        async with sessions() as s:
            case = await s.get(Case, case_id)
            if case.status != "error":
                return HTTPException(status_code=409, detail="not retryable")
            await asyncio.sleep(0.05)  # widen the window deterministically
            run_id = uuid.uuid4()
            case.status = "processing"
            case.pipeline_run_id = run_id
            await s.commit()
            return run_id

    results = await asyncio.gather(legacy_claim(), legacy_claim())
    winners = [r for r in results if isinstance(r, uuid.UUID)]
    assert len(winners) == 2, (
        "read-then-write is expected to admit both callers; if this now yields one "
        "winner the reproduction is wrong and the atomicity test proves nothing"
    )


async def test_claim_is_scoped_to_the_owning_practice(sessions, tenant):
    """Tenancy is enforced by the statement that writes, not only by the read
    before it (Hard rule 3)."""
    from app.models import Practice, User

    async with sessions() as s:
        other_practice = Practice(name="Other Practice")
        s.add(other_practice)
        await s.flush()
        outsider = User(
            practice_id=other_practice.id,
            cognito_sub=f"sub-{uuid.uuid4()}",
            email=f"{uuid.uuid4()}@heimdall.test",
            role="doctor",
        )
        s.add(outsider)
        await s.commit()

    case_id = await _make_case(sessions, tenant, "error")
    result = await _claim(sessions, case_id, outsider, _RETRYABLE)

    assert isinstance(result, HTTPException) and result.status_code == 409
    async with sessions() as s:
        untouched = await s.scalar(select(Case.status).where(Case.id == case_id))
    assert untouched == "error", "another practice's claim must not mutate the case"


async def test_claim_clears_a_previous_error_message(sessions, tenant):
    case_id = await _make_case(sessions, tenant, "error")
    async with sessions() as s:
        await s.execute(
            update(Case).where(Case.id == case_id).values(error_message="Processing failed (X).")
        )
        await s.commit()

    result = await _claim(sessions, case_id, tenant, _RETRYABLE)
    assert isinstance(result, uuid.UUID)

    async with sessions() as s:
        row = (
            await s.execute(select(Case.status, Case.error_message).where(Case.id == case_id))
        ).one()
    assert row.status == "processing"
    assert row.error_message is None, "a retry must not leave the old failure on screen"


@pytest.mark.parametrize("status", ["ready", "submitted", "resolved", "processing"])
async def test_retry_claim_rejects_ineligible_statuses(sessions, tenant, status):
    """Only `error` or genuinely stalled cases are retryable — a fresh
    `processing` case included, which is the anti-double-start case."""
    case_id = await _make_case(sessions, tenant, status)
    result = await _claim(sessions, case_id, tenant, _RETRYABLE)
    assert isinstance(result, HTTPException) and result.status_code == 409
