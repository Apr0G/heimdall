"""A phase that finishes after a newer run claimed the case must discard its work.

_run_phase re-reads the ownership token FOR UPDATE after the phase and before the
commit. These drive that path with a fake session, since the suite has no DB.
"""

import uuid

import pytest

from app.services import pipeline


class _FakeSession:
    def __init__(self, owner_at_start, owner_at_commit):
        self._owner_at_start = owner_at_start
        self._owner_at_commit = owner_at_commit
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, _model, _pk):
        return type("Case", (), {"pipeline_run_id": self._owner_at_start})()

    async def scalar(self, _stmt):
        # Stands in for the SELECT ... FOR UPDATE re-read after the phase.
        return self._owner_at_commit

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _patch(monkeypatch, session):
    monkeypatch.setattr(pipeline, "AsyncSessionLocal", lambda: session)


@pytest.mark.asyncio
async def test_commits_when_still_the_owner(monkeypatch):
    run_id = uuid.uuid4()
    session = _FakeSession(run_id, run_id)
    _patch(monkeypatch, session)

    ran = []

    async def phase(_s, _c):
        ran.append(True)

    assert await pipeline._run_phase(uuid.uuid4(), run_id, phase) is True
    assert ran == [True]
    assert session.committed and not session.rolled_back


@pytest.mark.asyncio
async def test_discards_results_when_superseded_mid_phase(monkeypatch):
    """Owner at the start, someone else by commit time — the window the old code
    committed straight through, overwriting the newer run's results."""
    run_id = uuid.uuid4()
    session = _FakeSession(run_id, uuid.uuid4())
    _patch(monkeypatch, session)

    async def phase(_s, _c):
        pass

    assert await pipeline._run_phase(uuid.uuid4(), run_id, phase) is False
    assert session.rolled_back and not session.committed


@pytest.mark.asyncio
async def test_skips_phase_entirely_when_already_superseded(monkeypatch):
    run_id = uuid.uuid4()
    session = _FakeSession(uuid.uuid4(), uuid.uuid4())
    _patch(monkeypatch, session)

    ran = []

    async def phase(_s, _c):
        ran.append(True)

    assert await pipeline._run_phase(uuid.uuid4(), run_id, phase) is False
    assert ran == [], "a superseded run must not spend Bedrock/Textract calls"
    assert not session.committed
