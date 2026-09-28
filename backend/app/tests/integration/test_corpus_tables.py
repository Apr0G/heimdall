"""Migration 0018 against a real Postgres: the export's BAA scope query, the
random record ids, the append-only release record, and the FK order the wipe
and disposal scripts rely on."""

import uuid

import pytest
from sqlalchemy import select, text

from app.models import Case, CorpusExport, CorpusExportEvent, CorpusRecord, Practice
from app.scripts import export_corpus


async def _practice(s, *, baa_version: str | None, signed: bool) -> Practice:
    p = Practice(
        name=f"Practice {uuid.uuid4()}",
        baa_version=baa_version,
        baa_signed_at=text("now()") if signed else None,
    )
    s.add(p)
    await s.flush()
    return p


async def _case(s, practice: Practice, user_id) -> Case:
    c = Case(practice_id=practice.id, created_by=user_id, case_type="appeal", status="ready")
    s.add(c)
    await s.flush()
    return c


async def test_only_practices_whose_baa_permits_deidentification_are_loaded(sessions, tenant):
    async with sessions() as s:
        permitted = await _practice(s, baa_version="v2", signed=True)
        unsigned = await _practice(s, baa_version="v2", signed=False)
        other_version = await _practice(s, baa_version="v1", signed=True)
        for p in (permitted, unsigned, other_version):
            await _case(s, p, tenant.id)
        await s.commit()
        bundles = await export_corpus.load_bundles(s, frozenset({"v2"}))
    practices = {b.case.practice_id for b in bundles}
    assert permitted.id in practices
    assert unsigned.id not in practices and other_version.id not in practices
    async with sessions() as s:
        assert await export_corpus.load_bundles(s, frozenset()) == []


async def test_corpus_records_link_random_ids_to_cases_and_events_are_append_only(sessions, tenant):
    async with sessions() as s:
        practice = await _practice(s, baa_version="v2", signed=True)
        case = await _case(s, practice, tenant.id)
        export = CorpusExport(
            ruleset_version="deid_v2",
            detector_versions={"engine": "test"},
            record_count=1,
            quarantine_key="exports/quarantine/x/corpus.jsonl",
            report_key="exports/quarantine/x/report.json",
        )
        s.add(export)
        await s.flush()
        record_id = uuid.uuid4()
        s.add(
            CorpusRecord(
                record_id=record_id, export_id=export.id, case_id=case.id, practice_id=practice.id
            )
        )
        s.add(CorpusExportEvent(export_id=export.id, event="exported", actor="export-task"))
        await s.commit()
        export_id = export.id

    async with sessions() as s:
        rec = await s.get(CorpusRecord, record_id)
        assert rec.case_id == case.id and rec.record_id != case.id
        event = (
            await s.scalars(
                select(CorpusExportEvent).where(CorpusExportEvent.export_id == export_id)
            )
        ).one()
        with pytest.raises(Exception, match="append-only"):
            await s.execute(
                text("UPDATE corpus_export_events SET actor = 'x' WHERE id = :id"), {"id": event.id}
            )
        await s.rollback()
        with pytest.raises(Exception, match="append-only"):
            await s.execute(
                text("DELETE FROM corpus_export_events WHERE id = :id"), {"id": event.id}
            )
        await s.rollback()
        # The mapping IS deletable: practice disposal severs the link.
        await s.execute(text("DELETE FROM corpus_records WHERE record_id = :id"), {"id": record_id})
        await s.rollback()
