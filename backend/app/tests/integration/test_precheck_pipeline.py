"""End-to-end pre-check pipeline against a real Postgres.

Everything except AWS is real: the migrated schema (0012/0013), synthetic NCCI
reference rows, the deterministic engine, the schema validation/guardrails, the
model_runs bookkeeping, and the status transitions. S3 returns canned bytes and
Bedrock returns canned JSON — the pipeline code path is exercised end to end.

All data synthetic (hard rule 1): Jane Doe-class initials, fabricated codes.
"""

import json
import uuid
from datetime import date

import pytest
from sqlalchemy import delete, select

from app.models import (
    Case,
    Document,
    Extraction,
    ModelRun,
    NcciLoad,
    NcciMue,
    NcciPtpEdit,
    RiskReport,
)
from app.services import claude_client, pipeline
from app.services.claude_client import _RawCall

pytestmark = pytest.mark.asyncio

_EXTRACTION_JSON = {
    "payer_name": "Test Payer Co",
    "plan_type": "commercial",
    "claim_number": "CLM-TEST-0001",
    "member_id": "TP000000000",
    "patient_initials": "J.D.",
    "date_of_service": "2026-08-01",
    "billed_amount_cents": 45000,
    "claim_lines": [
        {"cpt": "10001", "modifiers": [], "units": 1, "icd10": ["M54.50"], "pos": "11"},
        {"cpt": "10002", "modifiers": [], "units": 1, "icd10": ["M54.50"], "pos": "11"},
        {"cpt": "20553", "modifiers": [], "units": 4, "icd10": ["M54.50"], "pos": "11"},
    ],
    "icd10_codes": ["M54.50"],
    "clinical_summary": "Synthetic encounter for testing.",
    "confidence": 0.9,
}

_REVIEW_JSON = {
    "findings": [
        {
            "check_id": "em_level_mdm",
            "severity": "medium",
            "title": "Documentation is thin for the billed level",
            "predicted_carc": "CO-150",
            "explanation": "Synthetic explanation.",
            "suggested_fix": "Synthetic fix.",
        },
        {
            # Reserved deterministic id — the schema must drop this, so the
            # model can never spoof an NCCI finding.
            "check_id": "ncci_ptp",
            "severity": "high",
            "title": "Spoofed NCCI finding",
        },
    ]
}


async def _seed_ncci(sessions) -> None:
    async with sessions() as s:
        # The reference tables are shared across the session-scoped test DB —
        # clear them so re-runs and earlier failures can't collide on the PKs.
        for model in (NcciPtpEdit, NcciMue, NcciLoad):
            await s.execute(delete(model))
        s.add(
            NcciPtpEdit(
                column1="10001",
                column2="10002",
                effective_date=date(2020, 1, 1),
                deletion_date=None,
                modifier_indicator=1,
                rationale="Synthetic edit",
            )
        )
        s.add(
            NcciMue(
                hcpcs="20553",
                effective_quarter="2026Q3",
                mue_value=3,
                mai=3,
                rationale="Synthetic MUE",
            )
        )
        s.add(
            NcciLoad(
                kind="ptp", quarter="2026Q3", version_tag="2026Q3-vTESTr0", row_count=1, sha256="0"
            )
        )
        s.add(NcciLoad(kind="mue", quarter="2026Q3", version_tag="2026Q3", row_count=1, sha256="0"))
        await s.commit()


async def _seed_case(sessions, user, run_id) -> Case:
    async with sessions() as s:
        case = Case(
            practice_id=user.practice_id,
            created_by=user.id,
            status="processing",
            case_type="pre_check",
            pipeline_run_id=run_id,
        )
        s.add(case)
        await s.flush()
        for doc_type in ("claim", "clinical"):
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


def _patch_aws(monkeypatch, sessions, responses: list[dict]) -> list[str]:
    """Point the pipeline's session factories at the test DB, stub S3 with
    canned text, and feed Bedrock canned JSON per call. Returns the list of
    purposes claude was invoked for, in order."""
    monkeypatch.setattr(pipeline, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(claude_client, "AsyncSessionLocal", sessions)

    from app.services import document_extractor, s3

    monkeypatch.setattr(s3, "get_bytes", lambda key: b"synthetic document text")
    monkeypatch.setattr(s3, "put_text", lambda key, text: None)
    monkeypatch.setattr(s3, "head_object", lambda key: {"ContentLength": 10})
    monkeypatch.setattr(
        document_extractor, "digital_text_from_bytes", lambda data: "synthetic document text"
    )
    monkeypatch.setattr(document_extractor, "store_extracted_text", lambda key, text: None)

    calls: list[str] = []
    queue = list(responses)

    def fake_invoke(system, messages, max_tokens, temperature):
        calls.append(str(messages[0].get("content", ""))[:40])
        payload = queue.pop(0)
        return _RawCall(
            text=json.dumps(payload),
            input_tokens=100,
            output_tokens=50,
            latency_ms=5,
            stop_reason="end_turn",
            request_body="{}",
            response_body=json.dumps(payload),
        )

    monkeypatch.setattr(claude_client, "_invoke", fake_invoke)
    return calls


async def test_precheck_pipeline_end_to_end(sessions, tenant, monkeypatch):
    await _seed_ncci(sessions)
    run_id = uuid.uuid4()
    case = await _seed_case(sessions, tenant, run_id)
    _patch_aws(monkeypatch, sessions, [_EXTRACTION_JSON, _REVIEW_JSON])

    await pipeline.run_precheck_pipeline(case.id, run_id)

    async with sessions() as s:
        fresh = await s.get(Case, case.id)
        assert fresh.status == "ready"
        assert fresh.payer_name == "Test Payer Co"
        assert fresh.date_of_service == date(2026, 8, 1)
        assert fresh.denial_date is None and fresh.appeal_deadline is None

        extraction = await s.scalar(select(Extraction).where(Extraction.case_id == case.id))
        assert set(extraction.cpt_codes) == {"10001", "10002", "20553"}
        assert "member_id" not in (extraction.extracted_json or {})

        report = await s.scalar(select(RiskReport).where(RiskReport.case_id == case.id))
        assert report is not None
        checks = [(f["check_id"], f["severity"], f["source"]) for f in report.findings]
        # Deterministic: the PTP pair (indicator 1, no modifier -> high) and the
        # MUE violation (4 > 3, MAI 3 -> medium). Model: one real finding; the
        # spoofed ncci_ptp from the model was dropped by the schema filter.
        assert ("ncci_ptp", "high", "ncci") in checks
        assert ("ncci_mue", "medium", "ncci") in checks
        assert ("em_level_mdm", "medium", "model") in checks
        assert len([c for c in checks if c[2] == "model"]) == 1
        assert report.deterministic_count == 2 and report.model_count == 1
        assert report.overall_risk_band == "high"
        assert report.ncci_version_tag == "ptp 2026Q3-vTESTr0 / mue 2026Q3"

        runs = (
            await s.scalars(
                select(ModelRun).where(ModelRun.case_id == case.id).order_by(ModelRun.created_at)
            )
        ).all()
        assert [r.purpose for r in runs] == ["extraction", "pre_check_review"]
        assert all(r.status == "success" for r in runs)
        assert runs[0].prompt_version == "pc_extract_v1"
        assert runs[1].prompt_version == "pc_review_v1"


async def test_precheck_pipeline_no_billable_lines_errors(sessions, tenant, monkeypatch):
    run_id = uuid.uuid4()
    case = await _seed_case(sessions, tenant, run_id)
    empty = {**_EXTRACTION_JSON, "claim_lines": []}
    _patch_aws(monkeypatch, sessions, [empty])

    await pipeline.run_precheck_pipeline(case.id, run_id)

    async with sessions() as s:
        fresh = await s.get(Case, case.id)
        assert fresh.status == "error"
        # PHI-free typed name only — the frontend translates it.
        assert fresh.error_message == "Processing failed (NoBillableLinesError)."
        assert await s.scalar(select(RiskReport).where(RiskReport.case_id == case.id)) is None
