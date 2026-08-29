"""End-to-end appeal pipeline (run_full_pipeline) against a real Postgres.

Covers the revenue path the pre-check test already covers for pre-checks, and
regression-guards the H1 cross-connection deadlock: the SECOND document is
"scanned" (digital_text_from_bytes returns None), so _extract_one calls
_touch_if_owner mid-phase on the same cases row the loop heartbeat touches — the
exact sequence that previously self-deadlocked. If the heartbeat ever moves back
onto the phase session, this test hangs.

All data synthetic (hard rule 1).
"""

import asyncio
import json
import uuid

import pytest
from sqlalchemy import select

from app.models import AppealLetter, Case, Document, Extraction, ModelRun
from app.services import claude_client, document_extractor, pipeline, s3
from app.services.claude_client import _RawCall

pytestmark = pytest.mark.asyncio

_EXTRACTION = {
    "payer_name": "Test Payer Co",
    "plan_type": "commercial",
    "claim_number": "CLM-TEST-0001",
    "member_id": "MBRTEST0001",
    "patient_initials": "J.D.",
    "denial_date": "2026-08-01",
    "billed_amount_cents": 45000,
    "denied_amount_cents": 45000,
    "carc_codes": ["CO-50"],
    "group_codes": ["CO"],
    "cpt_codes": ["70551"],
    "icd10_codes": ["M54.50"],
    "confidence": 0.9,
}
_ANALYSIS = {
    "denial_category": "medical_necessity",
    "is_appealable": True,
    "appealability_reason": "CO-50 with clinical support is appealable.",
    "success_probability": 0.6,
    "reasoning_text": "Strong notes. This is an AI-generated estimate based on case "
    "characteristics, not a guarantee.",
    "recommended_appeal_level": "level_1_internal",
    "additional_documents_needed": [],
}
_LETTER = {
    "subject_line": "Appeal of denial for CLM-TEST-0001",
    "body": "To whom it may concern: " + ("This appeal is well supported. " * 30),
    "appeal_type": "level_1_internal",
    "attachments_referenced": [],
}

_BY_PURPOSE = {"extraction": _EXTRACTION, "analysis": _ANALYSIS, "letter_draft": _LETTER}


async def _seed_case(sessions, user, run_id) -> Case:
    async with sessions() as s:
        case = Case(
            practice_id=user.practice_id,
            created_by=user.id,
            status="processing",
            case_type="appeal",
            pipeline_run_id=run_id,
        )
        s.add(case)
        await s.flush()
        # denial first, then claim (the SCANNED one — second), then clinical.
        for doc_type in ("denial", "claim", "clinical"):
            s.add(
                Document(
                    case_id=case.id,
                    doc_type=doc_type,
                    s3_key=f"practices/{user.practice_id}/cases/{case.id}/{doc_type}/x.pdf",
                    uploaded_by=user.id,
                )
            )
        await s.commit()
        return case


def _patch_aws(monkeypatch, sessions):
    from app.core import hashing
    from app.core.config import settings

    # A pepper so member-ID hashing actually runs (else it degrades to None).
    monkeypatch.setattr(settings, "phi_hash_pepper", "test-pepper-not-a-real-secret")
    monkeypatch.setattr(hashing, "settings", settings, raising=False)
    monkeypatch.setattr(pipeline, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(claude_client, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(s3, "get_bytes", lambda key: b"%PDF-1.4 synthetic")
    monkeypatch.setattr(s3, "put_text", lambda key, text: None)
    monkeypatch.setattr(s3, "head_object", lambda key: {"ContentLength": 10})
    monkeypatch.setattr(s3, "extracted_text_key", lambda key: key + ".txt")

    # The "claim" doc is scanned → digital_text returns None → OCR/_touch path.
    def fake_digital(data):
        return None if b"CLAIMSCAN" in data else "synthetic digital text"

    # Distinguish the scanned doc by its bytes: get_bytes returns marker for claim.
    def fake_get_bytes(key):
        return b"%PDF CLAIMSCAN" if "/claim/" in key else b"%PDF-1.4 synthetic"

    monkeypatch.setattr(s3, "get_bytes", fake_get_bytes)
    monkeypatch.setattr(document_extractor, "digital_text_from_bytes", fake_digital)
    monkeypatch.setattr(document_extractor, "store_extracted_text", lambda key, text: None)
    monkeypatch.setattr(document_extractor, "run_textract", lambda key: "synthetic ocr text")

    def fake_invoke(system, messages, max_tokens, temperature):
        # Route by a marker the caller's prompt carries; simplest is purpose order,
        # but we key off which JSON the schema will accept. Use the system prompt.
        which = (
            "extraction"
            if "extraction specialist" in system
            else "analysis" if "appeals analyst" in system else "letter_draft"
        )
        payload = _BY_PURPOSE[which]
        body = json.dumps(payload)
        return _RawCall(
            text=body,
            input_tokens=100,
            output_tokens=50,
            latency_ms=5,
            stop_reason="end_turn",
            request_body="{}",
            response_body=body,
        )

    monkeypatch.setattr(claude_client, "_invoke", fake_invoke)


async def test_full_pipeline_end_to_end_with_scanned_second_doc(sessions, tenant, monkeypatch):
    run_id = uuid.uuid4()
    case = await _seed_case(sessions, tenant, run_id)
    _patch_aws(monkeypatch, sessions)

    # If the heartbeat regressed onto the phase session, this call hangs on the
    # scanned "claim" doc's mid-phase _touch_if_owner. There is no suite-wide
    # timeout (pytest-timeout is not installed), so the guard is explicit: a
    # regression fails here in a minute instead of sitting until the CI job
    # limit.
    await asyncio.wait_for(pipeline.run_full_pipeline(case.id, run_id), timeout=60)

    async with sessions() as s:
        fresh = await s.get(Case, case.id)
        assert fresh.status == "ready"
        # Member-ID hashing (hard rule 5) on the real appeal path.
        assert fresh.member_id_hash is not None
        assert fresh.member_id_hash != "MBRTEST0001"

        extraction = await s.scalar(select(Extraction).where(Extraction.case_id == case.id))
        assert "member_id" not in (extraction.extracted_json or {})
        assert extraction.carc_codes == ["CO-50"]

        letter = await s.scalar(select(AppealLetter).where(AppealLetter.case_id == case.id))
        assert letter is not None and letter.body.strip()

        runs = (
            await s.scalars(
                select(ModelRun).where(ModelRun.case_id == case.id).order_by(ModelRun.created_at)
            )
        ).all()
        assert [r.purpose for r in runs] == ["extraction", "analysis", "letter_draft"]
        assert [r.prompt_version for r in runs] == ["extract_v4", "analyze_v6", "letter_v6"]
