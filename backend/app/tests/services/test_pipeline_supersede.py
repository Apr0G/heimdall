"""A phase that finishes after a newer run claimed the case must discard its work.

_run_phase re-reads the ownership token FOR UPDATE after the phase and before the
commit. These drive that path with a fake session, since the suite has no DB.
"""

import io
import uuid
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from app.core.config import settings
from app.services import document_extractor, pipeline


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


# --- LOW-07: the upload guards run before ANY parser touches the bytes -------


def _pdf_with_pages(n: int) -> bytes:
    writer = PdfWriter()
    for _ in range(n):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class _FlushOnly:
    async def flush(self):
        pass


@pytest.fixture
def guarded(monkeypatch):
    """S3 returns `data`; every parser entry point after the guards is a trap."""

    def _install(data: bytes):
        monkeypatch.setattr(pipeline.s3, "get_bytes", lambda key: data)
        for name in ("form_fields_text", "digital_text_from_bytes", "run_textract"):

            def _trap(*a, _name=name, **k):
                raise AssertionError(f"{_name} ran before the upload guards")

            monkeypatch.setattr(document_extractor, name, _trap)
        return SimpleNamespace(id=uuid.uuid4(), s3_key="k", content_hash=None, text_source=None)

    return _install


async def test_page_cap_is_enforced_before_the_fillable_form_read(guarded, monkeypatch):
    """read_form walks every page's annotations with no cap of its own; a
    highly compressed 25 MB PDF with tens of thousands of pages used to reach
    it before digital_text_from_bytes ever applied the cap."""
    monkeypatch.setattr(settings, "max_document_pages", 2)
    doc = guarded(_pdf_with_pages(3))
    with pytest.raises(document_extractor.TooManyPagesError):
        await pipeline._extract_one(_FlushOnly(), doc, case_id=uuid.uuid4(), run_id=uuid.uuid4())


async def test_non_pdf_bytes_are_refused_before_any_parser(guarded):
    doc = guarded(b"<html>not a pdf</html>" * 100)
    with pytest.raises(document_extractor.NotAPdfError):
        await pipeline._extract_one(_FlushOnly(), doc, case_id=uuid.uuid4(), run_id=uuid.uuid4())


async def test_unparseable_pdf_fails_without_quoting_content(guarded):
    doc = guarded(b"%PDF-1.4\nSECRET-PATIENT-TEXT garbage")
    with pytest.raises(document_extractor.DocumentParseError) as exc:
        await pipeline._extract_one(_FlushOnly(), doc, case_id=uuid.uuid4(), run_id=uuid.uuid4())
    assert "SECRET-PATIENT-TEXT" not in str(exc.value)


async def test_a_pdf_within_the_cap_reaches_the_form_read(guarded, monkeypatch):
    doc = guarded(_pdf_with_pages(2))
    monkeypatch.setattr(document_extractor, "form_fields_text", lambda data: "label: value")
    monkeypatch.setattr(document_extractor, "digital_text_from_bytes", lambda data: None)
    stored = {}
    monkeypatch.setattr(
        document_extractor, "store_extracted_text", lambda key, text: stored.setdefault(key, text)
    )
    await pipeline._extract_one(_FlushOnly(), doc, case_id=uuid.uuid4(), run_id=uuid.uuid4())
    assert doc.text_source == "form_fields" and stored == {"k": "label: value"}
