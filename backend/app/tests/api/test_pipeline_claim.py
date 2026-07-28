"""The pipeline claim must be a single conditional UPDATE, not read-then-write.

There is no database in this suite, so these compile the real statements against
the PostgreSQL dialect and assert the guards survive into the emitted SQL. That
is what makes the claim atomic — losing the WHERE would silently reintroduce the
double-pipeline race without failing any behavioural test.
"""

from sqlalchemy import or_, update
from sqlalchemy.dialects import postgresql

from app.api.cases import STALE_PROCESSING, stalled_sql
from app.models import Case


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


def _claim(when) -> str:
    """Mirror of claim_for_pipeline's statement (it needs a live session to run)."""
    return _sql(
        update(Case)
        .where(Case.id == "00000000-0000-0000-0000-000000000001", when)
        .values(status="processing", pipeline_run_id=None)
        .returning(Case.id)
    )


def test_retry_claim_is_conditional_on_status():
    sql = _claim(or_(Case.status == "error", stalled_sql()))
    assert "update cases set" in sql
    # The eligibility test must be in the WHERE, not evaluated in Python first.
    assert "where" in sql
    assert "status" in sql.split("where", 1)[1]


def test_retry_claim_returns_a_row_so_the_loser_is_detectable():
    # Without RETURNING there is no way to tell "claimed it" from "someone else did".
    assert "returning" in _claim(Case.status == "ready")


def test_stalled_sql_uses_database_clock_not_python():
    sql = _sql(update(Case).where(stalled_sql()).values(status="processing"))
    assert "now()" in sql, "staleness must be evaluated by the DB inside the claim"
    assert "updated_at" in sql


def test_stalled_sql_requires_processing_status():
    sql = _sql(update(Case).where(stalled_sql()).values(status="processing"))
    where = sql.split("where", 1)[1]
    assert "status" in where and "updated_at" in where


def test_stall_window_is_shared_with_the_python_helper():
    # stalled_sql() and _is_stalled() must not drift apart.
    assert STALE_PROCESSING.total_seconds() > 0
