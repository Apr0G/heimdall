"""promote_corpus: the release is refused unless a named reviewer attests every
checklist item over the exact bytes in quarantine; a refusal is itself
recorded. Database and S3 faked."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models import AuditLog, CorpusExport, CorpusExportEvent
from app.scripts import promote_corpus
from app.scripts.promote_corpus import (
    CHECKLIST_ITEMS,
    PromoteRefused,
    parse_checklist,
    release_records,
)

EID = uuid.UUID("00000000-0000-4000-8000-000000000001")
CORPUS = (
    json.dumps(
        {"record_id": "r1", "deidentification": {"method": "safe-harbor", "released": False}}
    )
    + "\n"
    + json.dumps(
        {"record_id": "r2", "deidentification": {"method": "safe-harbor", "released": False}}
    )
    + "\n"
)
SHA = hashlib.sha256(CORPUS.encode()).hexdigest()
REPORT = json.dumps({"records": 2, "deidentification": {"status": "quarantined"}})
ALL_TRUE = json.dumps({k: True for k in CHECKLIST_ITEMS})


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, key):
        assert model is CorpusExport
        return self.store["export"] if key == EID else None

    async def scalars(self, stmt):
        return _Result(self.store["events"])

    def add(self, obj):
        self.store["added"].append(obj)

    async def commit(self):
        self.store["commits"] += 1


@pytest.fixture
def store():
    s = {
        "export": SimpleNamespace(id=EID),
        "events": [SimpleNamespace(event="exported")],
        "added": [],
        "commits": 0,
        "puts": {},
        "objects": {
            f"exports/quarantine/{EID}/corpus.jsonl": CORPUS.encode(),
            f"exports/quarantine/{EID}/report.json": REPORT.encode(),
        },
    }
    return s


def _run(store, **over):
    kwargs = dict(
        session_factory=lambda: _Session(store),
        export_id=EID,
        claimed_sha256=SHA,
        reviewer="reviewer-gh",
        checklist_raw=ALL_TRUE,
        now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        get_bytes=lambda key: store["objects"][key],
        put_text=lambda key, text: store["puts"].__setitem__(key, text),
    )
    kwargs.update(over)
    return promote_corpus.promote(**kwargs)


def _events(store):
    return [a for a in store["added"] if isinstance(a, CorpusExportEvent)]


async def test_release_flips_records_writes_event_audit_and_objects(store):
    report = await _run(store)
    events = _events(store)
    assert [e.event for e in events] == ["released"]
    assert events[0].actor == "reviewer-gh" and events[0].sha256 == SHA
    assert events[0].event_metadata["checklist"] == {k: True for k in CHECKLIST_ITEMS}
    audit = [a for a in store["added"] if isinstance(a, AuditLog)][0]
    assert audit.action == "corpus_release" and audit.resource_id == EID
    released = store["puts"][f"exports/released/{EID}/corpus.jsonl"]
    lines = [json.loads(line) for line in released.splitlines()]
    assert all(line["deidentification"]["released"] is True for line in lines)
    assert all(line["deidentification"]["released_at"].startswith("2026-09-28") for line in lines)
    assert report["release"]["reviewer"] == "reviewer-gh"
    assert report["release"]["reviewed_sha256"] == SHA
    assert report["deidentification"]["status"] == "released"
    assert json.loads(store["puts"][f"exports/released/{EID}/report.json"])["release"]["checklist"]


async def test_sha_mismatch_is_rejected_and_recorded(store):
    with pytest.raises(PromoteRefused, match="sha256"):
        await _run(store, claimed_sha256="0" * 64)
    assert [e.event for e in _events(store)] == ["rejected"]
    assert _events(store)[0].event_metadata == {"reason": "sha256 mismatch"}
    assert store["puts"] == {}


async def test_incomplete_checklist_is_rejected_and_recorded(store):
    partial = json.dumps({"names_reviewed": True})
    with pytest.raises(PromoteRefused, match="not attested"):
        await _run(store, checklist_raw=partial)
    assert [e.event for e in _events(store)] == ["rejected"]
    assert store["puts"] == {}


async def test_already_released_or_unknown_export_is_refused(store):
    store["events"].append(SimpleNamespace(event="released"))
    with pytest.raises(PromoteRefused, match="already released"):
        await _run(store)
    store["events"] = []
    with pytest.raises(PromoteRefused, match="no `exported` event"):
        await _run(store)
    with pytest.raises(PromoteRefused, match="no export"):
        await _run(store, export_id=uuid.uuid4())
    assert store["added"] == [] and store["puts"] == {}


async def test_empty_reviewer_is_refused(store):
    with pytest.raises(PromoteRefused, match="REVIEWER"):
        await _run(store, reviewer="  ")
    assert store["puts"] == {}


def test_parse_checklist_requires_every_item_true():
    assert parse_checklist(ALL_TRUE) == {k: True for k in CHECKLIST_ITEMS}
    with pytest.raises(PromoteRefused):
        parse_checklist(json.dumps({**json.loads(ALL_TRUE), "no_key_disclosed": False}))
    with pytest.raises(PromoteRefused):
        parse_checklist("not json")
    with pytest.raises(PromoteRefused):
        parse_checklist("[]")


def test_release_records_changes_only_the_release_flag():
    out = release_records(CORPUS, datetime(2026, 9, 28, tzinfo=UTC))
    before = [json.loads(line) for line in CORPUS.splitlines()]
    after = [json.loads(line) for line in out.splitlines()]
    for b, a in zip(before, after, strict=True):
        assert a["deidentification"].pop("released") is True
        assert a["deidentification"].pop("released_at").startswith("2026-09-28")
        b["deidentification"].pop("released")
        assert a == b
