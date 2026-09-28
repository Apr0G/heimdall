"""Detector layers: label mapping, the permitted exceptions, span union, the
Comprehend Medical client contract (fail closed on everything), the model
manifest check, and — where Presidio is installed — the spaCy-engine path.

All text synthetic. No network: Comprehend is a fake client."""

import hashlib
import json
import os

import pytest

from app.scripts import deid_detectors as dd
from app.scripts.deid_detectors import (
    ComprehendDetector,
    DetectorError,
    DetectorUnavailable,
    Span,
    apply_spans,
    disagreement,
    merge_spans,
    normalise,
    redact_with_detectors,
    verify_model_manifest,
)

# --- normalise / keep rules -------------------------------------------------------------


def test_unknown_entity_types_are_dropped_not_trusted():
    text = "Jane Doe seen"
    spans = normalise([(0, 8, "MYSTERY_TYPE", 0.99)], text, "comprehend", dd.COMPREHEND_LABELS)
    assert spans == []


def test_labels_are_mapped_and_codes_are_carved_out():
    text = "Mary Chen I48.91 seen"
    spans = normalise([(0, 16, "NAME", 0.9)], text, "comprehend", dd.COMPREHEND_LABELS)
    assert [(s.start, s.end, s.label) for s in spans] == [(0, 9, "NAME")]
    assert apply_spans(text, spans) == "[NAME] I48.91 seen"


@pytest.mark.parametrize(
    "snippet, entity",
    [
        ("2026", "DATE"),  # bare year is permitted
        ("year 2026", "DATE"),
        ("3 weeks", "DATE"),  # a duration is not a date
        ("daily", "DATE"),
        ("today", "DATE"),
        ("45-year-old", "DATE"),  # NER calls it a date; it is an age under 90
        ("45-year-old", "AGE"),
        ("aged 67", "AGE"),
        ("[NAME]", "NAME"),  # already a placeholder
        ("MRN", "NAME"),  # acronym
        ("RARC", "NAME"),
        ("IL", "ADDRESS"),  # state abbreviation
        ("Dx", "NAME"),  # clinical abbreviation
    ],
)
def test_permitted_exceptions_are_kept(snippet, entity):
    spans = normalise(
        [(0, len(snippet), entity, 0.95)], snippet, "comprehend", dd.COMPREHEND_LABELS
    )
    assert spans == [], (snippet, spans)


@pytest.mark.parametrize(
    "snippet, entity",
    [
        ("March 2026", "DATE"),  # month + year: a date element
        ("03/15", "DATE"),
        ("in March", "DATE"),
        ("92 years old", "AGE"),
        ("in her nineties", "AGE"),
        ("JANE DOE", "NAME"),  # two all-caps tokens is a name, not an acronym
        ("Springfield", "ADDRESS"),
        ("teacher", "PROFESSION"),
    ],
)
def test_identifiers_are_not_excused(snippet, entity):
    spans = normalise(
        [(0, len(snippet), entity, 0.95)], snippet, "comprehend", dd.COMPREHEND_LABELS
    )
    assert len(spans) == 1, (snippet, spans)


def test_org_keep_list_and_presidio_mapping():
    spans = normalise([(0, 8, "ORGANIZATION", 0.9)], "Medicare", "presidio", dd.PRESIDIO_LABELS)
    assert spans == []
    spans = normalise(
        [(0, 12, "ORGANIZATION", 0.9)], "Acme Widgets", "presidio", dd.PRESIDIO_LABELS
    )
    assert spans[0].label == "ORG"
    assert "NRP" not in dd.PRESIDIO_LABELS  # nationality / religion is not an identifier


# --- span algebra ----------------------------------------------------------------------------


def test_merge_spans_unions_overlaps_and_marks_both_sources():
    a = Span(0, 5, "NAME", "presidio", 0.8)
    b = Span(3, 9, "DATE", "comprehend", 0.95)
    c = Span(20, 25, "ID", "comprehend", 0.5)
    merged = merge_spans([c, b, a])
    assert merged == [Span(0, 9, "DATE", "both", 0.95), c]


def test_apply_spans_replaces_from_the_end_and_uses_label_tokens():
    text = "Jane Doe seen 03/15 at 12 Oak St"
    spans = [
        Span(0, 8, "NAME", "presidio", 0.9),
        Span(14, 19, "DATE", "comprehend", 0.9),
        Span(23, 32, "LOCATION", "comprehend", 0.9),
    ]
    assert apply_spans(text, spans) == "[NAME] seen [DATE] at [LOCATION]"


def test_disagreement_counts_spans_only_one_detector_found():
    a = [Span(0, 4, "NAME", "comprehend", 0.9), Span(10, 14, "DATE", "comprehend", 0.9)]
    b = [Span(0, 4, "NAME", "presidio", 0.9), Span(20, 24, "ID", "presidio", 0.9)]
    assert disagreement(a, b) == {"only_date_a": 1, "only_id_b": 1}


# --- Comprehend Medical detector ---------------------------------------------------------------


class _FakeComprehend:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[str] = []

    def detect_phi(self, Text):  # noqa: N803 — boto3 kwarg casing
        self.calls.append(Text)
        if self.error:
            raise self.error
        return self.responses.pop(0) if self.responses else {"Entities": [], "ModelVersion": "0"}


def _ent(text, needle, type_, score=0.9):
    i = text.index(needle)
    return {"BeginOffset": i, "EndOffset": i + len(needle), "Type": type_, "Score": score}


def test_comprehend_spans_threshold_and_model_version():
    text = "Jane Doe, age 45, seen 03/15 in Peoria."
    resp = {
        "Entities": [
            _ent(text, "Jane Doe", "NAME", 0.99),
            _ent(text, "45", "AGE", 0.9),
            _ent(text, "03/15", "DATE", 0.7),
            _ent(text, "Peoria", "ADDRESS", 0.1),  # below threshold: ignored
        ],
        "ModelVersion": "2.1.0",
    }
    det = ComprehendDetector(client=_FakeComprehend([resp]))
    spans = det.detect(text)
    assert {(s.label, text[s.start : s.end]) for s in spans} == {
        ("NAME", "Jane Doe"),
        ("DATE", "03/15"),
    }
    assert det.version()["model_versions"] == ["2.1.0"]
    assert det.version()["calls"] == 1 and det.version()["units"] == 1


def test_comprehend_truncated_result_is_fatal():
    det = ComprehendDetector(client=_FakeComprehend([{"Entities": [], "PaginationToken": "x"}]))
    with pytest.raises(DetectorError):
        det.detect("anything")


def test_comprehend_client_error_is_fatal():
    det = ComprehendDetector(client=_FakeComprehend(error=RuntimeError("ThrottlingException")))
    with pytest.raises(DetectorError):
        det.detect("anything")


def test_comprehend_chunks_long_text_on_line_boundaries_with_correct_offsets():
    line = "Jane Doe was seen.\n"
    text = line * 1500  # ~28 KB > the 18 KB chunk limit
    chunks = ComprehendDetector.chunks(text)
    assert len(chunks) == 2
    assert all(len(piece.encode()) <= ComprehendDetector.MAX_BYTES for _, piece in chunks)
    assert chunks[1][0] == len(chunks[0][1])
    assert "".join(p for _, p in chunks) == text
    # An entity in the second chunk maps back to the whole-text offset.
    fake = _FakeComprehend(
        [
            {"Entities": [], "ModelVersion": "1"},
            {"Entities": [_ent(chunks[1][1], "Jane Doe", "NAME")], "ModelVersion": "1"},
        ]
    )
    spans = ComprehendDetector(client=fake).detect(text)
    assert len(spans) == 1 and text[spans[0].start : spans[0].end] == "Jane Doe"
    assert spans[0].start >= chunks[1][0]


def test_comprehend_single_paragraph_over_the_limit_is_hard_cut():
    text = "x" * 40_000
    chunks = ComprehendDetector.chunks(text)
    assert "".join(p for _, p in chunks) == text
    assert all(len(p.encode()) <= ComprehendDetector.MAX_BYTES for _, p in chunks)


def test_redact_with_detectors_unions_and_reports():
    text = "Jane Doe seen 03/15"

    class _A:
        source = "comprehend"

        def detect(self, t):
            return [Span(0, 8, "NAME", "comprehend", 0.9)]

    class _B:
        source = "presidio"

        def detect(self, t):
            return [Span(14, 19, "DATE", "presidio", 0.9)]

    out, stats = redact_with_detectors(text, [_A(), _B()])
    assert out == "[NAME] seen [DATE]"
    assert stats == {
        "comprehend_name": 1,
        "presidio_date": 1,
        "only_name_a": 1,
        "only_date_b": 1,
    }
    assert redact_with_detectors(None, [_A()]) == (None, {})


# --- model manifest -----------------------------------------------------------------------------


def _fake_cache(tmp_path, model="Org/model", revision="abc123", files=None):
    snap = tmp_path / "hub" / f"models--{model.replace('/', '--')}" / "snapshots" / revision
    snap.mkdir(parents=True)
    digests = {}
    for name, body in (files or {"config.json": b"{}", "model.bin": b"weights"}).items():
        (snap / name).write_bytes(body)
        digests[name] = hashlib.sha256(body).hexdigest()
    manifest = tmp_path / "deid-model.json"
    manifest.write_text(json.dumps({"model": model, "revision": revision, "files": digests}))
    return manifest, snap


def test_manifest_verifies_and_records_its_own_hash(tmp_path, monkeypatch):
    manifest, _ = _fake_cache(tmp_path)
    monkeypatch.delenv("DEID_MODEL_MANIFEST_SHA256", raising=False)
    sha = verify_model_manifest(manifest, hf_cache=tmp_path / "hub")
    assert sha == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert os.environ["DEID_MODEL_MANIFEST_SHA256"] == sha


def test_manifest_refuses_a_modified_weight_file(tmp_path):
    manifest, snap = _fake_cache(tmp_path)
    (snap / "model.bin").write_bytes(b"tampered")
    with pytest.raises(DetectorUnavailable):
        verify_model_manifest(manifest, hf_cache=tmp_path / "hub")


def test_manifest_refuses_a_missing_snapshot_or_file(tmp_path):
    manifest, snap = _fake_cache(tmp_path)
    (snap / "config.json").unlink()
    with pytest.raises(DetectorUnavailable):
        verify_model_manifest(manifest, hf_cache=tmp_path / "hub")
    with pytest.raises(DetectorUnavailable):
        verify_model_manifest(manifest, hf_cache=tmp_path / "elsewhere")


# --- Presidio detector ----------------------------------------------------------------------------


def _require_presidio() -> None:
    """The CI deid job installs deid.lock and sets REQUIRE_DEID_TESTS=1; there a
    missing Presidio must FAIL, not skip. Laptops without the extras skip."""
    if os.environ.get("REQUIRE_DEID_TESTS"):
        try:
            import presidio_analyzer  # noqa: F401
        except ImportError:
            pytest.fail("presidio_analyzer is not installed — REQUIRE_DEID_TESTS=1 expects it")
        return
    pytest.importorskip("presidio_analyzer")


def test_unknown_engine_is_refused():
    with pytest.raises(DetectorUnavailable):
        dd.PresidioDetector(engine="magic")


def test_transformers_engine_is_unavailable_without_torch(monkeypatch):
    _require_presidio()
    if dd._installed("torch") and dd._installed("spacy-huggingface-pipelines"):
        pytest.skip("transformer stack installed here; covered by the image test")
    with pytest.raises(DetectorUnavailable):
        dd.PresidioDetector(engine="transformers")


@pytest.fixture(scope="module")
def spacy_detector():
    _require_presidio()
    try:
        return dd.PresidioDetector(engine="spacy", allow_list=["Aetna"])
    except DetectorUnavailable as exc:
        if os.environ.get("REQUIRE_DEID_TESTS"):
            raise
        pytest.skip(str(exc))


def test_spacy_engine_finds_free_floating_names_and_places(spacy_detector):
    out, _ = redact_with_detectors(
        "The report for Jane Doe was reviewed in Boston.", [spacy_detector]
    )
    assert "Jane Doe" not in out and "Boston" not in out


def test_spacy_engine_keeps_codes_ages_and_payer(spacy_detector):
    text = (
        "Aetna denied CPT 93306 for Mary Chen; Dx I48.91 and M23.205; RARC N115, M76, MA13; "
        "a 45-year-old seen for 3 weeks; CO-50."
    )
    out, _ = redact_with_detectors(text, [spacy_detector])
    for keep in (
        "Aetna",
        "93306",
        "I48.91",
        "M23.205",
        "N115",
        "M76",
        "MA13",
        "45-year-old",
        "CO-50",
    ):
        assert keep in out, (keep, out)
    assert "Mary Chen" not in out


def test_spacy_engine_version_is_recorded(spacy_detector):
    v = spacy_detector.version()
    assert v["engine"] == "spacy" and v["presidio_analyzer"] and v["spacy_model"]


def test_detect_is_deterministic(spacy_detector):
    text = "Jane Doe of Springfield was seen by Dr. Smith on March 3."
    assert spacy_detector.detect(text) == spacy_detector.detect(text)


# --- the production engine, where the pinned model is available (CI deid job) ----------------


@pytest.fixture(scope="module")
def transformer_detector():
    """Built exactly as the export builds it: manifest verified, model loaded
    from the verified snapshot path, hub offline."""
    if not os.environ.get("DEID_TRANSFORMER_AVAILABLE"):
        pytest.skip("pinned transformer not fetched here (set DEID_TRANSFORMER_AVAILABLE=1)")
    from pathlib import Path

    manifest = Path(__file__).resolve().parents[3] / "deid-model.json"
    verify_model_manifest(manifest)
    return dd.PresidioDetector(
        engine="transformers", transformer_model=str(dd.snapshot_dir(manifest))
    )


def test_transformer_engine_removes_names_dates_and_places(transformer_detector):
    text = (
        "Patient Jane Doe (DOB 03/15/1980) of Springfield was seen by Dr. Smith at "
        "Mercy Hospital on March 3 for CPT 93306; Dx I48.91. Employer: Acme Widgets."
    )
    out, stats = redact_with_detectors(text, [transformer_detector])
    for gone in ("Jane Doe", "03/15/1980", "Springfield", "Smith", "March 3"):
        assert gone not in out, (gone, out)
    for keep in ("93306", "I48.91"):
        assert keep in out, (keep, out)
    assert stats.get("presidio_name")


def test_transformer_engine_records_versions_and_manifest(transformer_detector):
    v = transformer_detector.version()
    assert v["engine"] == "transformers" and v["transformers"] and v["torch"]
    assert v["model_manifest"] == os.environ["DEID_MODEL_MANIFEST_SHA256"]


def test_transformer_engine_is_deterministic(transformer_detector):
    text = "Jane Doe of Springfield was seen by Dr. Smith on March 3, 2026."
    assert transformer_detector.detect(text) == transformer_detector.detect(text)
