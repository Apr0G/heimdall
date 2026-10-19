"""Practice disposal guards (LOW-22): refuses while any user is active, and
re-checks the practice prefixes AFTER the rows are gone so the printed
attestation is true at the moment it is printed.

The DB is a fake that answers the script's fixed statements; S3 is the FakeS3
from test_s3_purge. All ids synthetic.
"""

import json

import pytest

from app.scripts import dispose_practice, s3_purge
from app.tests.scripts.test_s3_purge import FakeS3

_PID = "00000000-0000-4000-8000-000000000001"
_PREFIX = f"practices/{_PID}/"


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, state: dict):
        self.state = state

    async def scalar(self, stmt, params=None):
        sql = str(stmt)
        if "FROM practices" in sql:
            return 1
        if "FROM users" in sql:
            return self.state["active_users"]
        if "count(*) FROM cases" in sql:
            return self.state["cases"]
        raise AssertionError(sql)

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.startswith("SELECT id FROM model_runs"):
            return _Result([])
        if sql.startswith("INSERT INTO audit_logs"):
            self.state["events"].append(("audit", params))
            return _Result([])
        assert sql.startswith("DELETE"), sql
        self.state["events"].append("delete")
        self.state["on_delete"]()
        return _Result([])


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _FakeEngine:
    def __init__(self, state):
        self.conn = _FakeConn(state)

    def connect(self):
        return _Ctx(self.conn)

    def begin(self):
        return _Ctx(self.conn)

    async def dispose(self):
        pass


def _wire(monkeypatch, *, active_users: int, on_delete=lambda: None):
    state = {
        "active_users": active_users,
        "cases": 1,
        "events": [],
        "on_delete": on_delete,
    }
    s3 = FakeS3({f"{_PREFIX}cases/c1/denial/doc.pdf": ["v2", "v1"]})
    monkeypatch.setenv("PRACTICE_ID", _PID)
    monkeypatch.setenv("DISPOSE_CONFIRM", _PID)
    monkeypatch.setenv("DISPOSE_EXPECT_CASES", "1")
    monkeypatch.setattr(dispose_practice, "create_async_engine", lambda url: _FakeEngine(state))
    monkeypatch.setattr(dispose_practice.boto3, "client", lambda *a, **k: s3)

    real_list = s3_purge.list_all_versions

    def recording_list(client, bucket, prefix):
        state["events"].append(("list", prefix))
        return real_list(client, bucket, prefix)

    monkeypatch.setattr(s3_purge, "list_all_versions", recording_list)
    return state, s3


async def test_refuses_while_any_user_is_active(monkeypatch):
    state, s3 = _wire(monkeypatch, active_users=2)
    with pytest.raises(SystemExit) as exc:
        await dispose_practice.main()
    assert "2 user(s)" in str(exc.value)
    assert s3.delete_calls == [] and state["events"] == []  # nothing touched


async def test_prefixes_are_rechecked_after_the_rows_are_gone(monkeypatch):
    state, s3 = _wire(monkeypatch, active_users=0)
    await dispose_practice.main()
    assert s3.versions == {}
    events = state["events"]
    last_delete = max(i for i, e in enumerate(events) if e == "delete")
    assert ("list", _PREFIX) in events[last_delete:]
    assert ("list", f"tmp-uploads/{_PID}/") in events[last_delete:]


async def test_disposal_is_recorded_in_the_audit_log_after_the_rows_are_gone(monkeypatch):
    """The destruction must leave a durable record, written in the same
    transaction as the deletes (after them), carrying counts and the actor
    only — never a key, filename or id list."""
    state, s3 = _wire(monkeypatch, active_users=0)
    monkeypatch.setenv("DISPOSE_ACTOR", "octocat")
    await dispose_practice.main()
    events = state["events"]
    audits = [e for e in events if isinstance(e, tuple) and e[0] == "audit"]
    assert len(audits) == 1
    last_delete = max(i for i, e in enumerate(events) if e == "delete")
    assert events.index(audits[0]) > last_delete
    params = audits[0][1]
    assert params["pid"] == _PID
    assert json.loads(params["metadata"]) == {
        "cases": 1,
        "model_runs": 0,
        "s3_object_versions": 2,
        "actor": "octocat",
    }


def test_audit_metadata_carries_counts_and_actor_only():
    meta = dispose_practice.disposal_audit_metadata(
        case_count=3, run_count=7, s3_deleted=11, actor="dispose-task"
    )
    assert set(meta) == {"cases", "model_runs", "s3_object_versions", "actor"}
    assert all(isinstance(v, (int, str)) for v in meta.values())


async def test_an_object_appearing_after_the_delete_fails_the_attestation(monkeypatch):
    holder = {}

    def sneak_upload():
        holder["s3"].versions[f"{_PREFIX}cases/c9/claim/late.pdf"] = ["v1"]

    state, s3 = _wire(monkeypatch, active_users=0, on_delete=sneak_upload)
    holder["s3"] = s3
    with pytest.raises(SystemExit) as exc:
        await dispose_practice.main()
    assert "INCOMPLETE" in str(exc.value)
    assert "delete" in state["events"]  # the rows were already gone — the message says so
