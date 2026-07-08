"""Export a training corpus: one JSONL record per case joining the input
(extraction + optional document text), the model's analysis, the generated
appeal letter (the output), and the reported outcome (the label). Writes to
s3://<bucket>/exports/corpus-<timestamp>.jsonl.

Contains PHI — this is for building your OWN training corpus and must be
de-identified before any model training. INCLUDE_DOC_TEXT=1 embeds the raw
extracted document text (heavier PHI); default off exports structured data only.

Run as a one-off in-VPC ECS task:  python -m app.scripts.export_corpus
"""

import asyncio
import json
import os
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Analysis, AppealLetter, Case, Document, Extraction, Outcome
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
        # A finalized letter is the real output; else the latest draft.
        letter = next((al for al in case_letters if al.finalized_at), None) or _latest(case_letters)
        case_outcomes = outcomes.get(case.id, [])
        outcome = _latest(case_outcomes, key="reported_at") if case_outcomes else None

        docs_out = []
        for doc in documents.get(case.id, []):
            entry = {"doc_type": doc.doc_type}
            if include_text:
                try:
                    raw = await asyncio.to_thread(s3.get_bytes, s3.extracted_text_key(doc.s3_key))
                    entry["text"] = raw.decode("utf-8", "replace")
                except Exception:  # noqa: BLE001 — a missing extraction shouldn't abort the export
                    entry["text"] = None
            docs_out.append(entry)

        records.append(
            {
                "case_id": str(case.id),
                "created_at": case.created_at.isoformat() if case.created_at else None,
                "status": case.status,
                "input": {
                    "payer_name": case.payer_name,
                    "plan_type": case.plan_type,
                    "claim_number": case.claim_number,
                    "patient_initials": case.patient_initials,
                    "date_of_service": (
                        case.date_of_service.isoformat() if case.date_of_service else None
                    ),
                    "denial_date": case.denial_date.isoformat() if case.denial_date else None,
                    "billed_amount_cents": case.billed_amount_cents,
                    "denied_amount_cents": case.denied_amount_cents,
                    "extraction": extraction.extracted_json if extraction else None,
                    "documents": docs_out,
                },
                "analysis": (
                    None
                    if analysis is None
                    else {
                        "denial_category": analysis.denial_category,
                        "is_appealable": analysis.is_appealable,
                        "appealability_reason": analysis.appealability_reason,
                        "success_probability": (
                            float(analysis.success_probability)
                            if analysis.success_probability is not None
                            else None
                        ),
                        "probability_band": analysis.probability_band,
                        "reasoning_text": analysis.reasoning_text,
                        "recommended_appeal_level": analysis.recommended_appeal_level,
                    }
                ),
                "output": {"appeal_letter": letter.body if letter else None},
                "label": (
                    None
                    if outcome is None
                    else {
                        "result": outcome.result,
                        "amount_recovered_cents": outcome.amount_recovered_cents,
                        "resolution_date": (
                            outcome.resolution_date.isoformat() if outcome.resolution_date else None
                        ),
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
        f"Exported {len(records)} cases ({labeled} with outcome labels) "
        f"-> s3://{settings.s3_bucket_name}/{key}"
    )


if __name__ == "__main__":
    asyncio.run(main())
