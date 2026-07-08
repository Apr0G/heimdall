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
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Analysis, AppealLetter, Case, Document, Extraction, Outcome
from app.scripts.deidentify import (
    SAFE_EXTRACTION_FIELDS,
    deid_year,
    hash_ref,
    redact_text,
)
from app.services import s3


def _group(rows):
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.case_id, []).append(row)
    return grouped


def _latest(rows, key="created_at"):
    return max(rows, key=lambda r: getattr(r, key)) if rows else None


async def main() -> None:
    include_text = os.environ.get("INCLUDE_DOC_TEXT") == "1"
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        cases = (await session.scalars(select(Case))).all()
        extractions = _group((await session.scalars(select(Extraction))).all())
        analyses = _group((await session.scalars(select(Analysis))).all())
        letters = _group((await session.scalars(select(AppealLetter))).all())
        outcomes = _group((await session.scalars(select(Outcome))).all())
        documents = _group((await session.scalars(select(Document))).all())

    records = []
    for case in cases:
        extraction = _latest(extractions.get(case.id, []))
        analysis = _latest(analyses.get(case.id, []))
        case_letters = letters.get(case.id, [])
        letter = next((al for al in case_letters if al.finalized_at), None) or _latest(case_letters)
        case_outcomes = outcomes.get(case.id, [])
        outcome = _latest(case_outcomes, key="reported_at") if case_outcomes else None

        raw = extraction.extracted_json if (extraction and extraction.extracted_json) else {}
        # Exact identifiers we captured for this case — redacted from all free text.
        known = [
            case.patient_initials,
            case.claim_number,
            raw.get("member_id"),
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
                    entry["text"] = redact_text(body.decode("utf-8", "replace"), known)
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
                    "clinical_summary": redact_text(raw.get("clinical_summary"), known),
                    "documents": docs_out,
                },
                "analysis": (
                    None
                    if analysis is None
                    else {
                        "denial_category": analysis.denial_category,
                        "is_appealable": analysis.is_appealable,
                        "appealability_reason": redact_text(analysis.appealability_reason, known),
                        "success_probability": (
                            float(analysis.success_probability)
                            if analysis.success_probability is not None
                            else None
                        ),
                        "probability_band": analysis.probability_band,
                        "reasoning_text": redact_text(analysis.reasoning_text, known),
                        "recommended_appeal_level": analysis.recommended_appeal_level,
                    }
                ),
                "output": {"appeal_letter": redact_text(letter.body if letter else None, known)},
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

    jsonl = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    key = f"exports/corpus-{datetime.now(UTC):%Y%m%d-%H%M%S}.jsonl"
    await asyncio.to_thread(s3.put_text, key, jsonl)

    labeled = sum(1 for r in records if r["label"] is not None)
    print(
        f"Exported {len(records)} de-identified cases ({labeled} with outcome labels) "
        f"-> s3://{settings.s3_bucket_name}/{key}"
    )


if __name__ == "__main__":
    asyncio.run(main())
