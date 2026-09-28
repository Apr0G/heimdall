"""Release a quarantined corpus export: the human prong of Safe Harbor, recorded.

45 CFR §164.514(b)(2)(ii) requires that the entity have no actual knowledge
that the remaining information could identify anyone. That is a determination a
person makes, so this script exists to make sure a person made it, and to write
down who, over which bytes, attesting to what:

  1. The reviewer downloads exports/quarantine/<export_id>/{corpus.jsonl,
     report.json, review.txt} with their own credentials, reads them, and works
     through the checklist below.
  2. They run the promote-corpus workflow with the export id, the sha256 of the
     corpus file THEY read, and every checklist item answered true.
  3. This task verifies the hash against the object in S3, refuses anything
     already released or never exported, rewrites every record with
     `deidentification.released = true`, copies corpus + report to
     exports/released/<export_id>/ (no lifecycle), and appends a `released`
     event — reviewer, sha256, checklist — plus an audit row. A hash mismatch or
     an unanswered item appends a `rejected` event and exits non-zero.

The checklist items are the guidance's own actual-knowledge examples (§3.6) and
the free-text warning (§3.10):

  names_reviewed      review.txt read; every surviving name-shaped string is a
                      payer, drug, anatomy or provider term — not a patient,
                      relative, employer or household member.
  no_occupation       no record states an occupation, title or role of the patient.
  no_public_event     no record describes a clinical event the reviewer knows to
                      have been publicised.
  no_small_population no record combines a rare condition with a practice small
                      enough that the reviewer could name the patient.
  no_key_disclosed    no recipient of this corpus has been given corpus_records,
                      the database, or any other means of re-identification.

Environment: EXPORT_ID, CORPUS_SHA256, REVIEWER (GitHub actor), CHECKLIST
(JSON object with the five keys above, all true).
"""

import asyncio
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import AuditLog, CorpusExport, CorpusExportEvent
from app.scripts.export_corpus import quarantine_keys, released_keys
from app.services import s3

CHECKLIST_ITEMS = (
    "names_reviewed",
    "no_occupation",
    "no_public_event",
    "no_small_population",
    "no_key_disclosed",
)


class PromoteRefused(RuntimeError):
    """The release was refused; a `rejected` event was (or will be) recorded."""


def parse_checklist(raw: str) -> dict[str, bool]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise PromoteRefused("CHECKLIST is not valid JSON") from exc
    if not isinstance(data, dict):
        raise PromoteRefused("CHECKLIST must be a JSON object")
    missing = [k for k in CHECKLIST_ITEMS if data.get(k) is not True]
    if missing:
        raise PromoteRefused(f"checklist items not attested: {missing}")
    return {k: True for k in CHECKLIST_ITEMS}


def release_records(jsonl: str, released_at: datetime) -> str:
    """Flip every record to released. Nothing else changes — the bytes the
    reviewer hashed are the bytes being released, plus this one flag."""
    out = []
    for line in jsonl.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        rec["deidentification"]["released"] = True
        rec["deidentification"]["released_at"] = released_at.isoformat()
        out.append(json.dumps(rec, ensure_ascii=False))
    return "\n".join(out) + "\n"


async def promote(
    *,
    session_factory,
    export_id: uuid.UUID,
    claimed_sha256: str,
    reviewer: str,
    checklist_raw: str,
    now: datetime | None = None,
    get_bytes=s3.get_bytes,
    put_text=s3.put_text,
) -> dict:
    stamp = now or datetime.now(UTC)
    reviewer = reviewer.strip()
    if not reviewer:
        raise PromoteRefused("REVIEWER is empty — a release must name the person who reviewed it")

    async with session_factory() as session:
        export = await session.get(CorpusExport, export_id)
        if export is None:
            raise PromoteRefused(f"no export {export_id}")
        events = (
            await session.scalars(
                select(CorpusExportEvent).where(CorpusExportEvent.export_id == export_id)
            )
        ).all()
        kinds = {e.event for e in events}
        if "exported" not in kinds:
            raise PromoteRefused("export has no `exported` event — nothing to release")
        if "released" in kinds:
            raise PromoteRefused("export was already released")

    async def _reject(reason: str) -> None:
        async with session_factory() as session:
            session.add(
                CorpusExportEvent(
                    export_id=export_id,
                    event="rejected",
                    actor=reviewer,
                    sha256=claimed_sha256,
                    event_metadata={"reason": reason},
                )
            )
            await session.commit()

    try:
        checklist = parse_checklist(checklist_raw)
    except PromoteRefused as exc:
        await _reject(str(exc))
        raise

    q = quarantine_keys(export_id)
    corpus_bytes = await asyncio.to_thread(get_bytes, q["corpus"])
    actual = hashlib.sha256(corpus_bytes).hexdigest()
    if actual != claimed_sha256.strip().lower():
        await _reject("sha256 mismatch")
        raise PromoteRefused(
            "the corpus in quarantine does not match the sha256 you reviewed — "
            "nothing was released"
        )
    report = json.loads((await asyncio.to_thread(get_bytes, q["report"])).decode("utf-8"))

    released = release_records(corpus_bytes.decode("utf-8"), stamp)
    released_sha = hashlib.sha256(released.encode("utf-8")).hexdigest()
    report["deidentification"]["status"] = "released"
    report["release"] = {
        "released_at": stamp.isoformat(),
        "reviewer": reviewer,
        "reviewed_sha256": actual,
        "released_sha256": released_sha,
        "checklist": checklist,
    }
    r = released_keys(export_id)

    async with session_factory() as session:
        session.add(
            CorpusExportEvent(
                export_id=export_id,
                event="released",
                actor=reviewer,
                sha256=actual,
                event_metadata={
                    "released_sha256": released_sha,
                    "checklist": checklist,
                    "released_key": r["corpus"],
                },
            )
        )
        session.add(
            AuditLog(
                action="corpus_release",
                resource_type="corpus_export",
                resource_id=export_id,
                event_metadata={
                    "reviewer": reviewer,
                    "sha256": actual,
                    "released_key": r["corpus"],
                },
            )
        )
        await session.commit()

    await asyncio.to_thread(put_text, r["corpus"], released)
    await asyncio.to_thread(put_text, r["report"], json.dumps(report, indent=2))
    return report


async def main() -> None:
    try:
        export_id = uuid.UUID(os.environ.get("EXPORT_ID", ""))
    except ValueError as exc:
        raise SystemExit("EXPORT_ID is not a UUID") from exc
    db = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(db, expire_on_commit=False)
    try:
        report = await promote(
            session_factory=session_factory,
            export_id=export_id,
            claimed_sha256=os.environ.get("CORPUS_SHA256", ""),
            reviewer=os.environ.get("REVIEWER", ""),
            checklist_raw=os.environ.get("CHECKLIST", ""),
        )
    except PromoteRefused as exc:
        raise SystemExit(f"REFUSED: {exc}") from exc
    finally:
        await db.dispose()
    keys = released_keys(export_id)
    print(
        f"Released export {export_id} ({report['records']} records) "
        f"by {report['release']['reviewer']}\n"
        f"  corpus: s3://{settings.s3_bucket_name}/{keys['corpus']}\n"
        f"  report: s3://{settings.s3_bucket_name}/{keys['report']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
