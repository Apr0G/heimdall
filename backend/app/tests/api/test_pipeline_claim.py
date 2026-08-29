"""The pipeline claim must be a single conditional UPDATE, not read-then-write.

There is no database in this suite, so these compile the real statements against
the PostgreSQL dialect and assert the guards survive into the emitted SQL. That
is what makes the claim atomic — losing the WHERE would silently reintroduce the
double-pipeline race without failing any behavioural test.
"""

import uuid

from sqlalchemy import or_, update
from sqlalchemy.dialects import postgresql

from app.api.cases import STALE_PROCESSING, _claim_stmt, _stalled_sql, _transition_stmt
from app.models import Case

CASE = uuid.UUID("00000000-0000-0000-0000-000000000001")
PRACTICE = uuid.UUID("00000000-0000-0000-0000-00000000000a")
RUN = uuid.UUID("00000000-0000-0000-0000-00000000000b")


def _compile(stmt):
    return stmt.compile(dialect=postgresql.dialect())


def _sql(stmt) -> str:
    return str(_compile(stmt)).lower()


def _claim(when) -> str:
    # The production statement itself (api.cases._claim_for_pipeline runs it).
    return _sql(_claim_stmt(CASE, PRACTICE, RUN, when))


def test_retry_claim_is_conditional_on_status():
    sql = _claim(or_(Case.status == "error", _stalled_sql()))
    assert "update cases set" in sql
    # The eligibility test must be in the WHERE, not evaluated in Python first.
    assert "where" in sql
    assert "status" in sql.split("where", 1)[1]


def test_retry_claim_is_tenant_scoped_in_the_same_where():
    # Hard rule 3: the claim must not be able to flip another practice's case.
    where = _claim(Case.status == "ready").split("where", 1)[1]
    assert "cases.practice_id" in where and "cases.id" in where
    params = _compile(_claim_stmt(CASE, PRACTICE, RUN, Case.status == "ready")).params
    assert PRACTICE in params.values() and CASE in params.values()


def test_retry_claim_returns_a_row_so_the_loser_is_detectable():
    # Without RETURNING there is no way to tell "claimed it" from "someone else did".
    assert "returning" in _claim(Case.status == "ready")


def test_retry_claim_stamps_the_run_token_and_clears_the_old_error():
    params = _compile(_claim_stmt(CASE, PRACTICE, RUN, Case.status == "error")).params
    assert RUN in params.values()
    assert "error_message" in _claim(Case.status == "error").split("set", 1)[1]


def test_stalled_sql_uses_database_clock_not_python():
    sql = _sql(update(Case).where(_stalled_sql()).values(status="processing"))
    assert "now()" in sql, "staleness must be evaluated by the DB inside the claim"
    assert "updated_at" in sql


def test_stalled_sql_requires_processing_status():
    sql = _sql(update(Case).where(_stalled_sql()).values(status="processing"))
    where = sql.split("where", 1)[1]
    assert "status" in where and "updated_at" in where


def test_stall_window_is_shared_with_the_python_helper():
    # _stalled_sql() and _is_stalled() must not drift apart: the interval the SQL
    # binds IS the constant the Python helper compares against.
    params = _compile(update(Case).where(_stalled_sql()).values(status="processing")).params
    assert STALE_PROCESSING in params.values()
    assert STALE_PROCESSING.total_seconds() > 0


# --- LOW-01: doctor-driven transitions use the same conditional-UPDATE shape --


def test_status_transition_is_conditional_tenant_scoped_and_detectable():
    stmt = _transition_stmt(CASE, PRACTICE, ("ready", "submitted"), status="submitted")
    sql = _sql(stmt)
    assert "update cases set" in sql
    where = sql.split("where", 1)[1]
    # The allowed-from statuses are evaluated by the database, not Python.
    assert "cases.status in" in where
    # Hard rule 3: the transition cannot flip another practice's case.
    assert "cases.practice_id" in where and "cases.id" in where
    assert "returning" in sql
    params = _compile(stmt).params
    assert PRACTICE in params.values() and CASE in params.values()
