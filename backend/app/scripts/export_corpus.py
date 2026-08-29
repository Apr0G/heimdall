"""Export a DE-IDENTIFIED training corpus: one JSONL record per case joining the
input (safe extraction fields + optional redacted document text), the model's
analysis, the generated appeal letter (the output), and the reported outcome (the
label). Writes to s3://<bucket>/exports/corpus-<timestamp>.jsonl.

Every free-text field (letter, reasoning, clinical summary, doc text) is run
through best-effort PHI redaction (see deidentify.py): captured identifiers are
removed, formatted PHI is masked, dates are generalized to the year, and claim
numbers become a salted hash. This is BEST-EFFORT, not certified Safe Harbor — a
free-floating name never captured structurally can still slip through free text;
review or run a PHI NER pass before using outside your BAA boundary.

Run as a one-off in-VPC ECS task:  python -m app.scripts.export_corpus
Set INCLUDE_DOC_TEXT=1 to embed the (redacted) raw extracted document text.
"""

import asyncio
import json
import os
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import hashing
from app.core.config import settings
from app.models import (
    Analysis,
    AppealLetter,
    Case,
    Document,
    Extraction,
    ModelRun,
    Outcome,
)
from app.scripts import deidentify
from app.scripts.deidentify import (
    SAFE_EXTRACTION_FIELDS,
    deid_year,
    hash_ref,
    redact_text,
    scan_residual,
    split_residual,
)
from app.services import s3


async def _member_id_from_archive(model_run: ModelRun | None) -> str | None:
    """Recover the raw member_id for exact-match redaction, from the ONE place that
    still holds it: the extraction call's archived Bedrock response in
    `model_runs/<id>/response.json`.

    Why this is needed at all: the export used to build its redaction key-set from
    `extracted_json["member_id"]`, but `services/extraction.py` writes that JSON
    with `exclude={"member_id"}` — deliberately, per hard rule 5. So the lookup
    returned None unconditionally and the member ID was silently never added to the
    redaction set. The exclusion meant to protect the identifier is what disabled
    its redaction.

    Reading it here introduces no new PHI storage: `security.tf` documents this
    archive as containing the raw value by design, under a 30-day lifecycle, inside
    the same BAA boundary. The value is used in memory to build the redaction set
    and is never written to the corpus.

    Returns None past the 30-day lifecycle window — which is exactly why the
    structural `_MBI` / `_MEMBER_ALNUM` patterns in deidentify.py exist as the
    layer that does not depend on having captured the value.
    """
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


def _write_review_list(names: set, stamp: datetime) -> str:
    """Candidate-name review list → a short-lived S3 key (never stdout). Returns
    the key. tmp-uploads/ is the one prefix with a 1-day expiry (security.tf)."""
    key = f"tmp-uploads/corpus-review/{stamp:%Y%m%d-%H%M%S}.txt"
    s3.put_text(key, "\n".join(sorted(names)) + "\n")
    return key


def _reidentification_risk(records: list[dict]) -> dict:
    """k-anonymity-style re-identification signal over the quasi-identifiers a
    statistician would weigh for an Expert Determination (§164.514(b)(1)). Reports
    the smallest equivalence-class size (k) and how many records are UNIQUE on the
    quasi-identifier combination — the highest re-id-risk rows. A tiny corpus will
    show mostly-unique (k=1); that's accurate signal that it isn't yet safe to treat
    as de-identified by statistical standards."""

    def qi(rec: dict) -> tuple:
        inp = rec.get("input", {})
        ana = rec.get("analysis") or {}
        return (
            inp.get("payer_name"),
            inp.get("plan_type"),
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


async def main() -> None:
    include_text = os.environ.get("INCLUDE_DOC_TEXT") == "1"
    # NER name redaction is ON unless explicitly disabled. Names in free prose
    # ("Jane Doe presents with…") are caught by nothing else, so an export with
    # NER silently unavailable is an export with names in it.
    use_ner = os.environ.get("USE_NER", "1") != "0"
    if use_ner and deidentify._ner_engines_or_none() is None:
        raise SystemExit(
            "ABORTED: NER name redaction is on but Presidio/spaCy are unavailable "
            "(install from deid.lock). Set USE_NER=0 only for a corpus you will "
            "review by hand before use."
        )

    # Preflight. hash_ref fails closed without a pepper, and it is called per
    # record — so without this the export would read the whole database, redact
    # every field, and only then die on the first claim_ref. Fail in the first
    # second instead, with an actionable message.
    if not hashing.is_configured():
        raise SystemExit(
            "PHI_HASH_PEPPER is not set. The corpus's claim_ref is an HMAC "
            "re-identification code (§164.514(c)); without the pepper it would be "
            "an offline-brute-forceable digest of the claim number, so the export "
            "refuses to run rather than emit one. Inject the secret "
            "(heimdall/phi-hash-pepper) into this task and re-run."
        )
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Appeals only: the corpus is (denial, appeal, outcome) triples, and a
        # pre-check case has no denial and no outcome — including one would emit
        # a hollow record that poisons the training labels.
        cases = (await session.scalars(select(Case).where(Case.case_type == "appeal"))).all()
        extractions = _group((await session.scalars(select(Extraction))).all())
        analyses = _group((await session.scalars(select(Analysis))).all())
        letters = _group((await session.scalars(select(AppealLetter))).all())
        outcomes = _group((await session.scalars(select(Outcome))).all())
        documents = _group((await session.scalars(select(Document))).all())
        model_runs = {
            run.id: run
            for run in (
                await session.scalars(select(ModelRun).where(ModelRun.purpose == "extraction"))
            ).all()
        }

    records = []
    recovered_member_ids = 0
    for case in cases:
        extraction = _latest(extractions.get(case.id, []))
        analysis = _latest(analyses.get(case.id, []))
        # Prefer a finalized letter, else the newest non-archived draft, else the
        # newest of anything. Archived letters are superseded advice (a re-analysis
        # flipped the case to not-appealable, or a newer draft replaced this one),
        # so they must not be the corpus's "output" label when a live one exists.
        case_letters = letters.get(case.id, [])
        letter = (
            next((al for al in case_letters if al.finalized_at), None)
            or _latest([al for al in case_letters if al.status != "archived"])
            or _latest(case_letters)
        )
        case_outcomes = outcomes.get(case.id, [])
        outcome = _latest(case_outcomes, key="reported_at") if case_outcomes else None

        raw = extraction.extracted_json if (extraction and extraction.extracted_json) else {}
        # Exact identifiers we captured for this case — redacted from all free text.
        # NOTE: `raw` never contains "member_id" (excluded at write time per hard
        # rule 5), so it is recovered from the model_run archive instead. Reading it
        # from `raw` here is a silent no-op and must not be reintroduced.
        member_id = (
            await _member_id_from_archive(model_runs.get(extraction.model_run_id))
            if extraction is not None
            else None
        )
        if member_id:
            recovered_member_ids += 1
        known = [
            case.patient_initials,
            case.claim_number,
            member_id,
            raw.get("patient_initials"),
            raw.get("claim_number"),
            raw.get("provider_name"),
            raw.get("provider_npi"),
            raw.get("prior_auth_number"),
        ]

        docs_out = []
        for doc in documents.get(case.id, []):
            entry = {"doc_type": doc.doc_type}
            if include_text:
                try:
                    body = await asyncio.to_thread(s3.get_bytes, s3.extracted_text_key(doc.s3_key))
                    entry["text"] = redact_text(body.decode("utf-8", "replace"), known, use_ner)
                except Exception:  # noqa: BLE001 — a missing extraction shouldn't abort the export
                    entry["text"] = None
            docs_out.append(entry)

        safe_extraction = {k: v for k, v in raw.items() if k in SAFE_EXTRACTION_FIELDS}

        records.append(
            {
                "case_id": str(case.id),  # internal random UUID, not derived from PHI
                "created_year": deid_year(case.created_at),
                "status": case.status,
                "claim_ref": hash_ref(case.claim_number) if case.claim_number else None,
                "deidentification": "best-effort",
                "input": {
                    "payer_name": case.payer_name,
                    "plan_type": case.plan_type,
                    "billed_amount_cents": case.billed_amount_cents,
                    "denied_amount_cents": case.denied_amount_cents,
                    "date_of_service_year": deid_year(case.date_of_service),
                    "denial_date_year": deid_year(case.denial_date),
                    "extraction": safe_extraction,
                    "clinical_summary": redact_text(raw.get("clinical_summary"), known, use_ner),
                    "documents": docs_out,
                },
                "analysis": (
                    None
                    if analysis is None
                    else {
                        "denial_category": analysis.denial_category,
                        "is_appealable": analysis.is_appealable,
                        "appealability_reason": redact_text(
                            analysis.appealability_reason, known, use_ner
                        ),
                        "success_probability": (
                            float(analysis.success_probability)
                            if analysis.success_probability is not None
                            else None
                        ),
                        "probability_band": analysis.probability_band,
                        "reasoning_text": redact_text(analysis.reasoning_text, known, use_ner),
                        "recommended_appeal_level": analysis.recommended_appeal_level,
                    }
                ),
                "output": {
                    "appeal_letter": redact_text(letter.body if letter else None, known, use_ner)
                },
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
        )

    await engine.dispose()

    # Validation report: re-scan the redacted free text for anything that still
    # looks like PHI. Formatted leaks must be zero; candidate_names is a human
    # review list (mostly payer/medical terms — a missed patient name shows here).
    leaks: Counter = Counter()
    review: Counter = Counter()
    names: set = set()
    for rec in records:
        texts = [rec["input"].get("clinical_summary"), rec["output"]["appeal_letter"]]
        if rec["analysis"]:
            texts += [
                rec["analysis"]["appealability_reason"],
                rec["analysis"]["reasoning_text"],
            ]
        texts += [d.get("text") for d in rec["input"]["documents"]]
        for value in texts:
            precise, broad, found = split_residual(scan_residual(value))
            leaks.update(precise)
            review.update(broad)
            names.update(found)

    # FAIL CLOSED on a formatted leak. These patterns are precise — an email, SSN,
    # phone, MBI or member-ID shape surviving redaction is a bug in the redactor,
    # not a false positive. The corpus lands in `exports/`, the one S3 prefix with
    # NO lifecycle expiry, so a leaked identifier there is retained indefinitely.
    # Writing it and mentioning the problem in a report nobody reads is not an
    # option (hard rule 9). The broad detectors (5-digit runs, letter+digit
    # tokens) fire on billing vocabulary and are reported, not gated on.
    if leaks and os.environ.get("ALLOW_RESIDUAL_LEAKS") != "1":
        raise SystemExit(
            "ABORTED: redaction left formatted identifiers in the corpus — "
            f"{dict(leaks)}. Nothing was written. Fix the patterns in "
            "deidentify.py and re-run; set ALLOW_RESIDUAL_LEAKS=1 only to "
            "deliberately export a corpus you have reviewed by hand."
        )
    # Name-shaped survivors gate the write too: with NER on, anything left is
    # either a benign term or a missed name, and the threshold forces a look.
    # Its only override is the threshold itself — ALLOW_RESIDUAL_LEAKS is about
    # formatted identifiers and must not switch this gate off as a side effect.
    max_names = int(os.environ.get("MAX_CANDIDATE_NAMES", "25"))
    if len(names) > max_names:
        raise SystemExit(
            f"ABORTED: {len(names)} name-shaped strings survived redaction (limit "
            f"{max_names}). Review them via DRY_RUN=1, which writes the list to a "
            "tmp-uploads/ key that expires in a day and prints only the key; "
            "raise MAX_CANDIDATE_NAMES only after that review."
        )

    labeled = sum(1 for r in records if r["label"] is not None)
    stamp = datetime.now(UTC)
    key = f"exports/corpus-{stamp:%Y%m%d-%H%M%S}.jsonl"
    report_key = key.replace(".jsonl", ".report.json")
    report = {
        "generated_at": stamp.isoformat(),
        "records": len(records),
        "labeled": labeled,
        "deidentification": "safe-harbor (best-effort; human review required)",
        "ner": use_ner,
        # The report lands in exports/ (no lifecycle), so it must not itself be
        # a list of the names that leaked: counts and irreversible tokens only.
        # The plaintext review list is written by DRY_RUN=1 to a key that
        # expires in a day, never here and never to the task's log.
        "residual": {
            "formatted_leaks": dict(leaks),  # expected empty — anything here is a bug
            "review_flags": dict(review),  # broad detectors: billing vocabulary mostly
            "candidate_name_count": len(names),
            "candidate_name_refs": sorted(hash_ref(n) for n in names)[:500],
        },
        # How many cases got EXACT-MATCH member-ID redaction (vs pattern-only). A
        # zero here across a non-empty corpus is the signature of the bug this
        # replaced: the key-set silently containing None for every case. Cases past
        # the model_runs 30-day lifecycle legitimately fall back to pattern-only.
        "member_id_redaction": {
            "exact_match_cases": recovered_member_ids,
            "total_cases": len(records),
            "pattern_only_cases": len(records) - recovered_member_ids,
        },
        # Statistical re-id signal for an Expert Determination (§164.514(b)(1)).
        "reidentification_risk": _reidentification_risk(records),
    }

    if os.environ.get("DRY_RUN") == "1":
        # The list exists because it may hold a patient name every detector
        # missed. This script only runs in-VPC as an ECS task, where stdout IS
        # CloudWatch (retained for the log group's lifetime) — so the names
        # never go to stdout (hard rule 2). They go to a tmp-uploads/ key,
        # which the bucket lifecycle expires after one day.
        review_key = await asyncio.to_thread(_write_review_list, names, stamp)
        print(
            f"DRY RUN — {len(records)} records, nothing exported. "
            f"{len(names)} candidate names written to "
            f"s3://{settings.s3_bucket_name}/{review_key} (expires in 1 day)."
        )
        return
    jsonl = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    await asyncio.to_thread(s3.put_text, key, jsonl)
    await asyncio.to_thread(s3.put_text, report_key, json.dumps(report, indent=2))

    warn = f"  ⚠️ formatted leaks: {dict(leaks)}" if leaks else ""
    if review:
        warn += f"\n  review flags (broad detectors, counts only): {dict(review)}"
    print(
        f"Exported {len(records)} de-identified cases ({labeled} with outcome labels)\n"
        f"  corpus: s3://{settings.s3_bucket_name}/{key}\n"
        f"  report: s3://{settings.s3_bucket_name}/{report_key} "
        f"({len(names)} candidate names to review){warn}"
    )


if __name__ == "__main__":
    asyncio.run(main())
