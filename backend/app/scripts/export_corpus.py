"""Export the training corpus to QUARANTINE, de-identified under HIPAA Safe Harbor
(45 CFR §164.514(b)(2)) — one JSONL record per appeal case joining the input
(safe extraction fields + redacted clinical summary), the model's analysis, the
generated appeal letter (the output), and the reported outcome (the label).

What "de-identified" means here, and what this script does and does not claim:

  * Every free-text field passes three layers — the rule set (deidentify.py),
    Presidio + a clinical transformer, and Amazon Comprehend Medical — and the
    union of everything any layer finds is removed. Then an independent, broader
    residual scan runs; a single precise residual aborts the run before any
    object is written. There is no environment variable that weakens a gate.
  * No field in a record is derived from PHI. `record_id` is minted at random
    here; the map back to `cases.id` is the `corpus_records` table and never
    leaves the database (§164.514(c)). Raw document text is not exported at all.
  * Only practices whose BAA version is in DEID_PERMITTED_BAA_VERSIONS are
    included (§164.502(d)(1): a business associate may de-identify only as its
    contract permits).
  * The output lands under exports/quarantine/<export_id>/ with a 30-day S3
    lifecycle and `deidentification.released = false`. It is STILL PHI. Safe
    Harbor's second prong — no actual knowledge that the remainder could
    identify anyone, §164.514(b)(2)(ii) — is a person's determination.
    promote_corpus.py records that person, the file hash and the checklist they
    attested to, and only then copies the corpus to exports/released/.

Run as a one-off in-VPC ECS task on the deid image:  python -m app.scripts.export_corpus
"""

import asyncio
import hashlib
import json
import os
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import (
    Analysis,
    AppealLetter,
    AuditLog,
    Case,
    CorpusExport,
    CorpusExportEvent,
    CorpusRecord,
    Document,
    Extraction,
    ModelRun,
    NcciMue,
    NcciPtpEdit,
    Outcome,
    Practice,
)
from app.scripts import deid_detectors
from app.scripts.deid_detectors import redact_with_detectors
from app.scripts.deidentify import (
    RULESET_VERSION,
    SAFE_EXTRACTION_FIELDS,
    deid_year,
    initials_variants,
    latest_year_in,
    redact_text,
    scan_residual,
    split_residual,
)
from app.services import s3

QUARANTINE_PREFIX = "exports/quarantine"
RELEASED_PREFIX = "exports/released"
# Name-shaped survivors above this count abort the run. A constant, not a
# setting: the fix for a noisy corpus is in the rules, never in the threshold.
CANDIDATE_NAME_REVIEW_LIMIT = 25


def quarantine_keys(export_id: uuid.UUID) -> dict[str, str]:
    base = f"{QUARANTINE_PREFIX}/{export_id}"
    return {
        "corpus": f"{base}/corpus.jsonl",
        "report": f"{base}/report.json",
        "review": f"{base}/review.txt",
    }


def released_keys(export_id: uuid.UUID) -> dict[str, str]:
    base = f"{RELEASED_PREFIX}/{export_id}"
    return {"corpus": f"{base}/corpus.jsonl", "report": f"{base}/report.json"}


def permitted_baa_versions() -> frozenset[str]:
    return frozenset(
        v.strip() for v in settings.deid_permitted_baa_versions.split(",") if v.strip()
    )


async def _member_id_from_archive(model_run: ModelRun | None) -> str | None:
    """Recover the raw member_id for exact-match redaction, from the ONE place that
    still holds it: the extraction call's archived Bedrock response in
    `model_runs/<id>/response.json` (30-day lifecycle, same BAA boundary). The
    value is used in memory to build the redaction set and is never written out.
    Past the lifecycle window this returns None and the structural member-id
    patterns in deidentify.py carry the class."""
    if model_run is None or not model_run.raw_response_s3_key:
        return None
    try:
        raw = await asyncio.to_thread(s3.get_bytes, model_run.raw_response_s3_key)
        payload = json.loads(raw.decode("utf-8", "replace"))
        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        value = json.loads(text[start : end + 1]).get("member_id")
        return str(value) if value else None
    except Exception:  # noqa: BLE001 — an expired archive must not abort the export
        return None


def _group(rows):
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.case_id, []).append(row)
    return grouped


def _latest(rows, key="created_at"):
    return max(rows, key=lambda r: getattr(r, key)) if rows else None


def practice_identifiers(practice: Practice | None) -> list[str]:
    """Practice name, NPI, tax id and address parts. Not patient identifiers
    under the rule (guidance §3.8) — removed anyway: customer confidentiality,
    and "small practice + rare code + state" is the actual-knowledge risk. The
    state itself stays (permitted geographic level, exported structurally)."""
    if practice is None:
        return []
    return [
        practice.name,
        practice.npi,
        practice.tax_id,
        practice.address_line1,
        practice.address_line2,
        practice.city,
        practice.zip,
    ]


def known_values(case: Case, raw: dict, member_id: str | None, practice: Practice | None) -> list:
    """Every exact value captured for this case that must not appear in text."""
    return [
        *initials_variants(case.patient_initials),
        *initials_variants(raw.get("patient_initials")),
        case.claim_number,
        member_id,
        raw.get("claim_number"),
        raw.get("provider_name"),
        raw.get("provider_npi"),
        raw.get("prior_auth_number"),
        *practice_identifiers(practice),
    ]


def _reidentification_risk(records: list[dict]) -> dict:
    """k-anonymity-style re-identification signal over the quasi-identifiers a
    statistician would weigh for an Expert Determination (§164.514(b)(1)).
    Informational under Safe Harbor; the evidence an expert would ask for."""

    def qi(rec: dict) -> tuple:
        inp = rec.get("input", {})
        ana = rec.get("analysis") or {}
        return (
            inp.get("payer_name"),
            inp.get("plan_type"),
            inp.get("state"),
            inp.get("denial_date_year"),
            inp.get("date_of_service_year"),
            ana.get("denial_category"),
            inp.get("denied_amount_cents"),
        )

    groups = Counter(qi(r) for r in records)
    sizes = list(groups.values())
    unique = sum(1 for s in sizes if s == 1)
    return {
        "quasi_identifiers": [
            "payer_name",
            "plan_type",
            "state",
            "denial_date_year",
            "date_of_service_year",
            "denial_category",
            "denied_amount_cents",
        ],
        "distinct_combinations": len(groups),
        "k_anonymity_min": min(sizes) if sizes else 0,
        "records_unique_on_qi": unique,
        "pct_unique": round(100 * unique / len(records), 1) if records else 0.0,
    }


@dataclass
class CaseBundle:
    """Everything the export reads for one case, loaded up front."""

    case: Case
    practice: Practice | None
    extraction: Extraction | None
    analysis: Analysis | None
    letter: AppealLetter | None
    outcome: Outcome | None
    documents: list[Document] = field(default_factory=list)
    member_id: str | None = None


def pick_letter(case_letters: Sequence[AppealLetter]) -> AppealLetter | None:
    """Prefer a finalized letter, else the newest non-archived draft, else the
    newest of anything. Archived letters are superseded advice (a re-analysis
    flipped the case to not-appealable, or a newer draft replaced this one),
    so they must not be the corpus's "output" label when a live one exists."""
    return (
        next((al for al in case_letters if al.finalized_at), None)
        or _latest([al for al in case_letters if al.status != "archived"])
        or _latest(case_letters)
    )


def redact_field(
    text: str | None,
    known: list,
    *,
    latest_year: int,
    codes: frozenset[str],
    detectors: Sequence[object],
) -> tuple[str | None, dict[str, int]]:
    """rules -> detectors (union) for one field."""
    ruled = redact_text(text, known, latest_year=latest_year, known_codes=codes)
    return redact_with_detectors(ruled, detectors)


def build_record(
    bundle: CaseBundle,
    *,
    record_id: uuid.UUID,
    export_id: uuid.UUID,
    codes: frozenset[str],
    detectors: Sequence[object],
) -> tuple[dict, dict[str, int]]:
    """One corpus record plus the detector statistics for it. Pure apart from
    the detector calls."""
    case, extraction, analysis, letter, outcome = (
        bundle.case,
        bundle.extraction,
        bundle.analysis,
        bundle.letter,
        bundle.outcome,
    )
    raw = extraction.extracted_json if (extraction and extraction.extracted_json) else {}
    known = known_values(case, raw, bundle.member_id, bundle.practice)
    texts = [
        raw.get("clinical_summary"),
        analysis.appealability_reason if analysis else None,
        analysis.reasoning_text if analysis else None,
        letter.body if letter else None,
    ]
    latest_year = latest_year_in(
        texts,
        deid_year(case.created_at),
        deid_year(case.date_of_service),
        deid_year(case.denial_date),
        deid_year(outcome.resolution_date) if outcome else None,
    )
    stats: Counter = Counter()

    def _r(value: str | None) -> str | None:
        out, st = redact_field(
            value, known, latest_year=latest_year, codes=codes, detectors=detectors
        )
        stats.update(st)
        return out

    safe_extraction = {k: v for k, v in raw.items() if k in SAFE_EXTRACTION_FIELDS}
    record = {
        "record_id": str(record_id),
        "export_id": str(export_id),
        "deidentification": {
            "method": "safe-harbor",
            "ruleset": RULESET_VERSION,
            "released": False,
        },
        "created_year": deid_year(case.created_at),
        "status": case.status,
        "input": {
            "payer_name": case.payer_name,
            "plan_type": case.plan_type,
            "state": bundle.practice.state if bundle.practice else None,
            "billed_amount_cents": case.billed_amount_cents,
            "denied_amount_cents": case.denied_amount_cents,
            "date_of_service_year": deid_year(case.date_of_service),
            "denial_date_year": deid_year(case.denial_date),
            "extraction": safe_extraction,
            "clinical_summary": _r(raw.get("clinical_summary")),
            "document_types": sorted(d.doc_type for d in bundle.documents),
        },
        "analysis": (
            None
            if analysis is None
            else {
                "denial_category": analysis.denial_category,
                "is_appealable": analysis.is_appealable,
                "appealability_reason": _r(analysis.appealability_reason),
                "success_probability": (
                    float(analysis.success_probability)
                    if analysis.success_probability is not None
                    else None
                ),
                "probability_band": analysis.probability_band,
                "reasoning_text": _r(analysis.reasoning_text),
                "recommended_appeal_level": analysis.recommended_appeal_level,
            }
        ),
        "output": {"appeal_letter": _r(letter.body if letter else None)},
        "label": (
            None
            if outcome is None
            else {
                "result": outcome.result,
                "amount_recovered_cents": outcome.amount_recovered_cents,
                "resolution_year": deid_year(outcome.resolution_date),
            }
        ),
    }
    return record, dict(stats)


def record_texts(rec: dict) -> list[str | None]:
    texts = [rec["input"].get("clinical_summary"), rec["output"]["appeal_letter"]]
    if rec["analysis"]:
        texts += [rec["analysis"]["appealability_reason"], rec["analysis"]["reasoning_text"]]
    return texts


def residual_gate(records: list[dict], codes: frozenset[str]) -> tuple[Counter, Counter, set]:
    """Re-scan every redacted field. Returns (precise leaks, review-only counts,
    candidate names). The caller aborts on any precise leak and on too many
    candidate names — never on the review-only counts (billing vocabulary)."""
    leaks: Counter = Counter()
    review: Counter = Counter()
    names: set = set()
    for rec in records:
        for value in record_texts(rec):
            precise, broad, found = split_residual(scan_residual(value, codes))
            leaks.update(precise)
            review.update(broad)
            names.update(found)
    return leaks, review, names


def build_detectors(engine: str) -> list[object]:
    """Detector B (Presidio) and Detector A (Comprehend Medical). Both required."""
    transformer_model = settings.deid_transformer_model
    if engine == "transformers":
        from pathlib import Path

        manifest = Path(settings.deid_model_manifest)
        deid_detectors.verify_model_manifest(manifest)
        # Load from the verified snapshot PATH, never from the repo id: no hub
        # lookup, no network, and only the revision the manifest names.
        transformer_model = str(deid_detectors.snapshot_dir(manifest))
    presidio = deid_detectors.PresidioDetector(
        engine=engine,
        spacy_model=settings.deid_spacy_model,
        transformer_model=transformer_model,
    )
    comprehend = deid_detectors.ComprehendDetector(region=settings.aws_region)
    return [presidio, comprehend]


def preflight() -> str:
    """Everything that can be checked before a row is read. Returns the engine."""
    if not permitted_baa_versions():
        raise SystemExit(
            "ABORTED: DEID_PERMITTED_BAA_VERSIONS is empty. A business associate may "
            "de-identify PHI only as the BAA permits (45 CFR 164.502(d)(1)); list the "
            "BAA versions whose text grants it, or export nothing."
        )
    engine = settings.deid_nlp_engine
    if settings.app_env == "production" and engine != "transformers":
        raise SystemExit(
            "ABORTED: DEID_NLP_ENGINE must be 'transformers' in production. The spaCy "
            "engine is a laptop/CI fallback whose recall does not support a Safe Harbor "
            "'removed' claim."
        )
    return engine


async def load_ncci_codes(session) -> frozenset[str]:
    """Every CPT/HCPCS code the NCCI tables know. Distinguishes a five-digit
    billing code from a five-digit ZIP or account number in text."""
    c1 = (await session.scalars(select(NcciPtpEdit.column1).distinct())).all()
    c2 = (await session.scalars(select(NcciPtpEdit.column2).distinct())).all()
    mue = (await session.scalars(select(NcciMue.hcpcs).distinct())).all()
    return frozenset(str(c).strip().upper() for c in [*c1, *c2, *mue] if c)


async def load_bundles(session, permitted: frozenset[str]) -> list[CaseBundle]:
    """Every appeal case of every practice whose BAA permits de-identification.
    Cross-tenant by design — this is the one job that reads across practices,
    and the scope gate is the BAA version, not a practice id."""
    rows = (
        await session.execute(
            select(Case, Practice)
            .join(Practice, Practice.id == Case.practice_id)
            .where(
                Case.case_type == "appeal",
                Practice.baa_signed_at.is_not(None),
                Practice.baa_version.in_(permitted),
            )
        )
    ).all()
    if not rows:
        return []
    case_ids = [c.id for c, _ in rows]
    extractions = _group(
        (await session.scalars(select(Extraction).where(Extraction.case_id.in_(case_ids)))).all()
    )
    analyses = _group(
        (await session.scalars(select(Analysis).where(Analysis.case_id.in_(case_ids)))).all()
    )
    letters = _group(
        (
            await session.scalars(select(AppealLetter).where(AppealLetter.case_id.in_(case_ids)))
        ).all()
    )
    outcomes = _group(
        (await session.scalars(select(Outcome).where(Outcome.case_id.in_(case_ids)))).all()
    )
    documents = _group(
        (await session.scalars(select(Document).where(Document.case_id.in_(case_ids)))).all()
    )
    model_runs = {
        run.id: run
        for run in (
            await session.scalars(
                select(ModelRun).where(
                    ModelRun.purpose == "extraction", ModelRun.case_id.in_(case_ids)
                )
            )
        ).all()
    }
    bundles = []
    for case, practice in rows:
        extraction = _latest(extractions.get(case.id, []))
        case_outcomes = outcomes.get(case.id, [])
        bundles.append(
            CaseBundle(
                case=case,
                practice=practice,
                extraction=extraction,
                analysis=_latest(analyses.get(case.id, [])),
                letter=pick_letter(letters.get(case.id, [])),
                outcome=_latest(case_outcomes, key="reported_at") if case_outcomes else None,
                documents=documents.get(case.id, []),
                member_id=(
                    await _member_id_from_archive(model_runs.get(extraction.model_run_id))
                    if extraction is not None
                    else None
                ),
            )
        )
    return bundles


def build_report(
    *,
    export_id: uuid.UUID,
    stamp: datetime,
    records: list[dict],
    leaks: Counter,
    review: Counter,
    names: set,
    detector_stats: Counter,
    versions: dict,
    codes_count: int,
    recovered_member_ids: int,
    corpus_sha256: str,
) -> dict:
    """Counts and versions only — the report lands next to the corpus, so it
    must never itself be a list of what leaked."""
    labeled = sum(1 for r in records if r["label"] is not None)
    return {
        "export_id": str(export_id),
        "generated_at": stamp.isoformat(),
        "records": len(records),
        "labeled": labeled,
        "corpus_sha256": corpus_sha256,
        "deidentification": {
            "method": "safe-harbor",
            "status": "quarantined — PHI until a `released` event exists",
            "ruleset": RULESET_VERSION,
            "detectors": versions,
            "ncci_codes_known": codes_count,
        },
        "residual": {
            "formatted_leaks": dict(leaks),  # zero by construction — the gate aborted otherwise
            "review_flags": dict(review),  # broad detectors: billing vocabulary mostly
            "candidate_name_count": len(names),
        },
        "detector_stats": dict(detector_stats),
        "member_id_redaction": {
            "exact_match_cases": recovered_member_ids,
            "total_cases": len(records),
            "pattern_only_cases": len(records) - recovered_member_ids,
        },
        "reidentification_risk": _reidentification_risk(records),
    }


async def export(
    *,
    session_factory,
    detectors: Sequence[object],
    engine_name: str,
    now: datetime | None = None,
    put_text=s3.put_text,
) -> dict:
    """The whole run, with collaborators injected for the tests. Returns the
    report. Raises SystemExit on any gate."""
    stamp = now or datetime.now(UTC)
    export_id = uuid.uuid4()
    permitted = permitted_baa_versions()

    async with session_factory() as session:
        codes = await load_ncci_codes(session)
        if not codes:
            raise SystemExit(
                "ABORTED: the NCCI tables are empty. The export needs the CPT/HCPCS code "
                "set to tell a billing code from a ZIP code; run load-ncci first."
            )
        bundles = await load_bundles(session, permitted)
    if not bundles:
        raise SystemExit(
            "ABORTED: no appeal case belongs to a practice whose BAA version is in "
            f"DEID_PERMITTED_BAA_VERSIONS ({sorted(permitted)}). Nothing to export."
        )

    records: list[dict] = []
    mapping: list[tuple[uuid.UUID, CaseBundle]] = []
    detector_stats: Counter = Counter()
    for bundle in bundles:
        record_id = uuid.uuid4()
        record, stats = build_record(
            bundle, record_id=record_id, export_id=export_id, codes=codes, detectors=detectors
        )
        detector_stats.update(stats)
        records.append(record)
        mapping.append((record_id, bundle))

    # FAIL CLOSED on a precise residual. These patterns are precise — an email,
    # SSN, phone, MBI, member-ID, labeled id, partial date or initials shape
    # surviving three layers is a bug in the redactor, not a false positive.
    # Nothing is written; there is no override.
    leaks, review, names = residual_gate(records, codes)
    if leaks:
        raise SystemExit(
            "ABORTED: redaction left identifiers in the corpus — "
            f"{dict(leaks)}. Nothing was written. Fix the patterns in deidentify.py "
            "(and add the fixture) and re-run."
        )
    if len(names) > CANDIDATE_NAME_REVIEW_LIMIT:
        raise SystemExit(
            f"ABORTED: {len(names)} name-shaped strings survived redaction (limit "
            f"{CANDIDATE_NAME_REVIEW_LIMIT}). Nothing was written. This is a rules "
            "problem, not a threshold problem: run the redactor over the offending "
            "letters locally and add the missing pattern."
        )

    jsonl = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    corpus_sha = hashlib.sha256(jsonl.encode("utf-8")).hexdigest()
    versions = {
        getattr(d, "source", type(d).__name__): d.version()  # type: ignore[attr-defined]
        for d in detectors
    }
    versions["engine"] = engine_name
    versions["image_digest"] = os.environ.get("IMAGE_DIGEST")
    keys = quarantine_keys(export_id)
    report = build_report(
        export_id=export_id,
        stamp=stamp,
        records=records,
        leaks=leaks,
        review=review,
        names=names,
        detector_stats=detector_stats,
        versions=versions,
        codes_count=len(codes),
        recovered_member_ids=sum(1 for _, b in mapping if b.member_id),
        corpus_sha256=corpus_sha,
    )

    # Database first: the mapping and the `exported` event exist before any
    # object does. A failed upload then leaves a run with no objects, which is
    # harmless; the reverse would leave objects with no record of who made them.
    async with session_factory() as session:
        session.add(
            CorpusExport(
                id=export_id,
                ruleset_version=RULESET_VERSION,
                detector_versions=versions,
                record_count=len(records),
                quarantine_key=keys["corpus"],
                report_key=keys["report"],
            )
        )
        for record_id, bundle in mapping:
            session.add(
                CorpusRecord(
                    record_id=record_id,
                    export_id=export_id,
                    case_id=bundle.case.id,
                    practice_id=bundle.case.practice_id,
                )
            )
        session.add(
            CorpusExportEvent(
                export_id=export_id,
                event="exported",
                actor="export-task",
                sha256=corpus_sha,
                event_metadata={
                    "records": len(records),
                    "candidate_name_count": len(names),
                    "review_flags": dict(review),
                },
            )
        )
        session.add(
            AuditLog(
                action="corpus_export",
                resource_type="corpus_export",
                resource_id=export_id,
                event_metadata={
                    "records": len(records),
                    "ruleset": RULESET_VERSION,
                    "engine": engine_name,
                    "quarantine_key": keys["corpus"],
                },
            )
        )
        await session.commit()

    await asyncio.to_thread(put_text, keys["corpus"], jsonl)
    await asyncio.to_thread(put_text, keys["report"], json.dumps(report, indent=2))
    # The candidate-name list exists because it may hold a patient name every
    # layer missed. It goes next to the corpus (same 30-day expiry), never to
    # stdout — in-VPC, stdout IS CloudWatch (hard rule 2).
    await asyncio.to_thread(put_text, keys["review"], "\n".join(sorted(names)) + "\n")
    return report


async def main() -> None:
    engine_name = preflight()
    try:
        detectors = build_detectors(engine_name)
    except deid_detectors.DetectorUnavailable as exc:
        raise SystemExit(f"ABORTED: detector unavailable — {exc}") from exc

    db = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(db, expire_on_commit=False)
    try:
        report = await export(
            session_factory=session_factory, detectors=detectors, engine_name=engine_name
        )
    except deid_detectors.DetectorError as exc:
        raise SystemExit(f"ABORTED: detector failure — {exc}. Nothing was written.") from exc
    finally:
        await db.dispose()

    keys = quarantine_keys(uuid.UUID(report["export_id"]))
    print(
        f"Quarantined {report['records']} records ({report['labeled']} labeled) as export "
        f"{report['export_id']}\n"
        f"  corpus: s3://{settings.s3_bucket_name}/{keys['corpus']}\n"
        f"  report: s3://{settings.s3_bucket_name}/{keys['report']}\n"
        f"  review: s3://{settings.s3_bucket_name}/{keys['review']} "
        f"({report['residual']['candidate_name_count']} candidate names)\n"
        f"  sha256: {report['corpus_sha256']}\n"
        "STILL PHI. Review, then run promote-corpus with this export id and sha256."
    )


if __name__ == "__main__":
    asyncio.run(main())
