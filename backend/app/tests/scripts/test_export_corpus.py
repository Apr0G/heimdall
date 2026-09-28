"""export_corpus: what leaves the task and what stops it. The database and S3
are faked; no detector model is loaded — detectors are stubs, so these tests
pin the export's CONTRACT (record shape, gates, ordering, no overrides), not
the detectors' recall (test_deid_detectors.py / test_deidentify.py)."""

import json
import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.models import AuditLog, CorpusExport, CorpusExportEvent, CorpusRecord
from app.scripts import export_corpus
from app.scripts.deid_detectors import DetectorError, Span
from app.scripts.export_corpus import (
    CaseBundle,
    build_record,
    known_values,
    permitted_baa_versions,
    pick_letter,
    quarantine_keys,
    released_keys,
    residual_gate,
)

CODES = frozenset({"99213", "93306", "73721"})
_PRACTICE_ID = uuid.UUID("00000000-0000-4000-8000-00000000000a")


def _bundle(letter_body="Dear Reviewer, we appeal CPT 93306 for our patient.", **over):
    case = SimpleNamespace(
        id=uuid.uuid4(),
        practice_id=_PRACTICE_ID,
        status="ready",
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        payer_name="Aetna",
        plan_type="commercial",
        claim_number="CLM-TEST-0001",
        patient_initials="J.D.",
        date_of_service=date(2026, 2, 10),
        denial_date=date(2026, 2, 20),
        billed_amount_cents=45000,
        denied_amount_cents=45000,
    )
    practice = SimpleNamespace(
        id=_PRACTICE_ID,
        name="Springfield Family Practice",
        npi="1234567890",
        tax_id="12-3456789",
        address_line1="12 Oak Street",
        address_line2=None,
        city="Springfield",
        state="IL",
        zip="62704",
    )
    extraction = SimpleNamespace(
        extracted_json={
            "payer_name": "Aetna",
            "plan_type": "commercial",
            "claim_number": "CLM-TEST-0001",
            "patient_initials": "J.D.",
            "provider_name": "Dr. Alice Provider",
            "provider_npi": "1234567890",
            "prior_auth_number": "AUTH-555",
            "cpt_codes": ["93306"],
            "icd10_codes": ["I48.91"],
            "carc_codes": ["CO-50"],
            "clinical_summary": "The patient J.D. had an echo (93306) for I48.91 on 02/10/2026.",
            "confidence": 0.9,
        },
        model_run_id=None,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    analysis = SimpleNamespace(
        denial_category="medical_necessity",
        is_appealable=True,
        appealability_reason="CO-50 is appealable for J.D.",
        success_probability=0.7,
        probability_band="high",
        reasoning_text="Echo 93306 was justified. This is an AI-generated estimate.",
        recommended_appeal_level="level_1_internal",
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    letter = SimpleNamespace(
        body=letter_body,
        status="draft",
        finalized_at=None,
        created_at=datetime(2026, 3, 2, tzinfo=UTC),
    )
    outcome = SimpleNamespace(
        result="overturned",
        amount_recovered_cents=45000,
        resolution_date=date(2026, 5, 1),
        reported_at=datetime(2026, 5, 2, tzinfo=UTC),
    )
    docs = [SimpleNamespace(doc_type="denial"), SimpleNamespace(doc_type="claim")]
    kwargs = dict(
        case=case,
        practice=practice,
        extraction=extraction,
        analysis=analysis,
        letter=letter,
        outcome=outcome,
        documents=docs,
        member_id="W1A2B3C4D",
    )
    kwargs.update(over)
    return CaseBundle(**kwargs)


class _NoopDetector:
    source = "presidio"

    def detect(self, text):
        return []

    def version(self):
        return {"engine": "stub"}


class _Comprehend(_NoopDetector):
    source = "comprehend"


class _FailingDetector(_NoopDetector):
    def detect(self, text):
        raise DetectorError("boom")


# --- record shape ---------------------------------------------------------------------------


def test_record_carries_no_case_id_no_hash_no_document_text():
    rid, eid = uuid.uuid4(), uuid.uuid4()
    rec, _ = build_record(_bundle(), record_id=rid, export_id=eid, codes=CODES, detectors=[])
    dumped = json.dumps(rec)
    assert rec["record_id"] == str(rid) and rec["export_id"] == str(eid)
    assert "case_id" not in dumped and "claim_ref" not in dumped
    assert "documents" not in rec["input"] and rec["input"]["document_types"] == ["claim", "denial"]
    assert rec["deidentification"] == {
        "method": "safe-harbor",
        "ruleset": "deid_v2",
        "released": False,
    }
    # Structured fields: years only, state only, amounts exact.
    assert rec["input"]["date_of_service_year"] == 2026 and rec["input"]["denial_date_year"] == 2026
    assert rec["input"]["state"] == "IL" and rec["input"]["denied_amount_cents"] == 45000
    assert rec["label"]["resolution_year"] == 2026
    assert set(rec["input"]["extraction"]) <= export_corpus.SAFE_EXTRACTION_FIELDS
    # The record must not name the case's identifiers anywhere.
    for leaked in (
        "CLM-TEST-0001",
        "J.D.",
        "W1A2B3C4D",
        "1234567890",
        "12-3456789",
        "Alice Provider",
        "AUTH-555",
    ):
        assert leaked not in dumped, leaked


def test_record_ids_are_random_per_call():
    a, _ = build_record(
        _bundle(), record_id=uuid.uuid4(), export_id=uuid.uuid4(), codes=CODES, detectors=[]
    )
    b, _ = build_record(
        _bundle(), record_id=uuid.uuid4(), export_id=uuid.uuid4(), codes=CODES, detectors=[]
    )
    assert a["record_id"] != b["record_id"]


def test_practice_identifiers_and_initials_are_in_the_known_set():
    b = _bundle()
    known = known_values(b.case, b.extraction.extracted_json, b.member_id, b.practice)
    for v in (
        "JD",
        "J D",
        "J.D.",
        "CLM-TEST-0001",
        "W1A2B3C4D",
        "Springfield Family Practice",
        "12 Oak Street",
        "62704",
    ):
        assert v in known, v


def test_letter_text_loses_practice_letterhead_but_keeps_codes():
    body = (
        "Springfield Family Practice, NPI 1234567890, Tax ID 12-3456789\n12 Oak Street\n"
        "Springfield, IL 62704\nMarch 3, 2026\nRe: Appeal of Denied Claim #CLM-TEST-0001 for J.D., "
        "DOS 02/10/2026\nWe appeal CPT 93306 for I48.91 denied under CO-50.\n"
        "Sincerely,\nDr. Alice Provider"
    )
    rec, _ = build_record(
        _bundle(letter_body=body),
        record_id=uuid.uuid4(),
        export_id=uuid.uuid4(),
        codes=CODES,
        detectors=[],
    )
    letter = rec["output"]["appeal_letter"]
    for gone in (
        "Springfield Family",
        "1234567890",
        "12-3456789",
        "Oak Street",
        "62704",
        "March 3",
        "CLM-TEST",
        "J.D.",
        "02/10",
        "Alice Provider",
    ):
        assert gone not in letter, (gone, letter)
    for keep in ("93306", "I48.91", "CO-50", "IL"):
        assert keep in letter, (keep, letter)


def test_detector_spans_are_applied_after_the_rules():
    class _Names(_NoopDetector):
        def detect(self, text):
            i = text.find("Zorp Yelling")
            return [Span(i, i + 12, "NAME", "presidio", 0.9)] if i >= 0 else []

    rec, stats = build_record(
        _bundle(letter_body="Zorp Yelling had 93306."),
        record_id=uuid.uuid4(),
        export_id=uuid.uuid4(),
        codes=CODES,
        detectors=[_Names()],
    )
    assert rec["output"]["appeal_letter"] == "[NAME] had 93306."
    assert stats == {"presidio_name": 1}


def test_pick_letter_prefers_finalized_then_live_draft_then_anything():
    fin = SimpleNamespace(finalized_at=1, status="finalized", created_at=1)
    draft = SimpleNamespace(finalized_at=None, status="draft", created_at=2)
    archived = SimpleNamespace(finalized_at=None, status="archived", created_at=3)
    assert pick_letter([archived, draft, fin]) is fin
    assert pick_letter([archived, draft]) is draft
    assert pick_letter([archived]) is archived
    assert pick_letter([]) is None


def test_residual_gate_reads_every_text_field():
    rec, _ = build_record(
        _bundle(), record_id=uuid.uuid4(), export_id=uuid.uuid4(), codes=CODES, detectors=[]
    )
    rec["analysis"]["reasoning_text"] = "leftover a@b.com"
    leaks, _, _ = residual_gate([rec], CODES)
    assert leaks == {"email": 1}


def test_keys_and_permitted_versions(monkeypatch):
    eid = uuid.UUID("00000000-0000-4000-8000-000000000001")
    assert quarantine_keys(eid)["corpus"] == f"exports/quarantine/{eid}/corpus.jsonl"
    assert released_keys(eid)["report"] == f"exports/released/{eid}/report.json"
    monkeypatch.setattr(export_corpus.settings, "deid_permitted_baa_versions", " v2 ,v3,,")
    assert permitted_baa_versions() == frozenset({"v2", "v3"})
    monkeypatch.setattr(export_corpus.settings, "deid_permitted_baa_versions", "")
    assert permitted_baa_versions() == frozenset()


# --- the run: gates and ordering --------------------------------------------------------------


class _Session:
    """Records adds; the loaders are monkeypatched so no statement is executed."""

    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        self.store["added"].append(obj)

    async def commit(self):
        self.store["commits"] += 1


@pytest.fixture
def run(monkeypatch):
    store = {"added": [], "commits": 0, "puts": {}}
    monkeypatch.setattr(export_corpus.settings, "deid_permitted_baa_versions", "v2")

    async def _codes(session):
        return store.get("codes", CODES)

    async def _bundles(session, permitted):
        assert permitted == frozenset({"v2"})
        return store.get("bundles", [_bundle(), _bundle()])

    monkeypatch.setattr(export_corpus, "load_ncci_codes", _codes)
    monkeypatch.setattr(export_corpus, "load_bundles", _bundles)

    async def _go(detectors=None):
        return await export_corpus.export(
            session_factory=lambda: _Session(store),
            detectors=detectors if detectors is not None else [_NoopDetector(), _Comprehend()],
            engine_name="stub",
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            put_text=lambda key, text: store["puts"].__setitem__(key, text),
        )

    store["go"] = _go
    return store


async def test_successful_export_writes_rows_then_three_objects(run):
    report = await run["go"]()
    added = run["added"]
    exports = [a for a in added if isinstance(a, CorpusExport)]
    records = [a for a in added if isinstance(a, CorpusRecord)]
    events = [a for a in added if isinstance(a, CorpusExportEvent)]
    audits = [a for a in added if isinstance(a, AuditLog)]
    assert len(exports) == 1 and len(records) == 2 and run["commits"] == 1
    assert [e.event for e in events] == ["exported"] and events[0].sha256 == report["corpus_sha256"]
    assert audits[0].action == "corpus_export" and audits[0].resource_id == exports[0].id
    assert {r.practice_id for r in records} == {_PRACTICE_ID}
    eid = uuid.UUID(report["export_id"])
    keys = quarantine_keys(eid)
    assert set(run["puts"]) == set(keys.values())
    lines = [json.loads(line) for line in run["puts"][keys["corpus"]].splitlines()]
    assert len(lines) == 2 and all(line["deidentification"]["released"] is False for line in lines)
    assert {line["record_id"] for line in lines} == {str(r.record_id) for r in records}
    assert report["deidentification"]["status"].startswith("quarantined")
    assert report["residual"]["formatted_leaks"] == {}
    # The report names no identifier: only counts, versions and hashes.
    dumped = json.dumps(report)
    for leaked in ("J.D.", "CLM-TEST", "W1A2B3C4D", "Springfield"):
        assert leaked not in dumped


async def test_no_permitted_practice_aborts_before_any_write(run):
    run["bundles"] = []
    with pytest.raises(SystemExit, match="no appeal case"):
        await run["go"]()
    assert run["added"] == [] and run["puts"] == {}


async def test_empty_ncci_tables_abort(run):
    run["codes"] = frozenset()
    with pytest.raises(SystemExit, match="NCCI"):
        await run["go"]()
    assert run["puts"] == {}


async def test_a_precise_residual_aborts_and_no_environment_variable_can_override(run, monkeypatch):
    class _Leaky(_NoopDetector):
        def detect(self, text):
            return []

    # A detector stub that "un-redacts": simulate a rules gap by injecting a leak
    # through the letter body that the rules do not cover — an email with a
    # placeholder-breaking shape is caught, so use the residual scanner's own
    # broader net: a labeled MRN after a placeholder the rules leave alone.
    run["bundles"] = [_bundle(letter_body="see [NAME] and mail a@b.com")]
    monkeypatch.setattr(export_corpus, "redact_field", lambda text, known, **kw: (text, {}))
    for var in (
        "ALLOW_RESIDUAL_LEAKS",
        "USE_NER",
        "INCLUDE_DOC_TEXT",
        "MAX_CANDIDATE_NAMES",
        "DRY_RUN",
    ):
        monkeypatch.setenv(var, "1")
    with pytest.raises(SystemExit, match="left identifiers"):
        await run["go"]([_Leaky(), _Comprehend()])
    assert run["added"] == [] and run["puts"] == {}


async def test_too_many_candidate_names_abort(run, monkeypatch):
    # Letters only: the other text fields are blanked so the ONLY residual is the
    # name-shaped bigrams, which are a review signal, not a precise leak.
    names = " ".join(f"Zorp{c} Yelling{c}" for c in "abcdefghijklmnopqrstuvwxyz")
    bundle = _bundle(letter_body=names, analysis=None)
    bundle.extraction.extracted_json["clinical_summary"] = None
    run["bundles"] = [bundle]
    monkeypatch.setattr(export_corpus, "redact_field", lambda text, known, **kw: (text, {}))
    with pytest.raises(SystemExit, match="name-shaped"):
        await run["go"]()
    assert run["puts"] == {}


async def test_detector_failure_propagates_and_nothing_is_written(run):
    with pytest.raises(DetectorError):
        await run["go"]([_FailingDetector(), _Comprehend()])
    assert run["added"] == [] and run["puts"] == {}


def test_preflight_refuses_empty_baa_list_and_spacy_in_production(monkeypatch):
    monkeypatch.setattr(export_corpus.settings, "deid_permitted_baa_versions", "")
    with pytest.raises(SystemExit, match="DEID_PERMITTED_BAA_VERSIONS"):
        export_corpus.preflight()
    monkeypatch.setattr(export_corpus.settings, "deid_permitted_baa_versions", "v2")
    monkeypatch.setattr(export_corpus.settings, "app_env", "production")
    monkeypatch.setattr(export_corpus.settings, "deid_nlp_engine", "spacy")
    with pytest.raises(SystemExit, match="transformers"):
        export_corpus.preflight()
    monkeypatch.setattr(export_corpus.settings, "deid_nlp_engine", "transformers")
    assert export_corpus.preflight() == "transformers"


def test_no_legacy_knobs_survive_in_the_source():
    import inspect

    src = inspect.getsource(export_corpus)
    for knob in (
        "ALLOW_RESIDUAL_LEAKS",
        "USE_NER",
        "INCLUDE_DOC_TEXT",
        "MAX_CANDIDATE_NAMES",
        "DRY_RUN",
        "hash_ref",
        "best-effort",
    ):
        assert knob not in src, knob
