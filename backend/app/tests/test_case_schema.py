"""Bounds and contract of the case request/response schemas (LOW-11, LOW-13):
free text that is persisted and echoed is capped, and the risk report carries
the id a client echoes back when applying edits."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.case import (
    CorrectedClaimRequest,
    NewCaseDocument,
    OutcomeRequest,
    RiskReportDetail,
    UploadSlotRequest,
)


def test_outcome_notes_are_bounded():
    OutcomeRequest(result="overturned", notes="n" * 2000)
    with pytest.raises(ValidationError):
        OutcomeRequest(result="overturned", notes="n" * 2001)


@pytest.mark.parametrize(
    "build",
    [
        lambda name: UploadSlotRequest(doc_type="claim", filename=name),
        lambda name: NewCaseDocument(doc_type="claim", s3_key="tmp-uploads/p/x.pdf", filename=name),
    ],
    ids=["upload-slot", "new-case-document"],
)
def test_filenames_are_bounded_where_they_are_presigned_and_where_they_are_stored(build):
    build("f" * 255)
    with pytest.raises(ValidationError):
        build("f" * 256)


def test_risk_report_detail_carries_its_id():
    base = dict(
        overall_risk_band="low",
        findings=[],
        deterministic_count=0,
        model_count=0,
        ncci_version_tag=None,
        created_at=datetime.now(UTC),
    )
    report_id = uuid4()
    assert RiskReportDetail(id=report_id, **base).id == report_id
    with pytest.raises(ValidationError):
        RiskReportDetail(**base)


def test_corrected_claim_request_report_id_is_optional_but_must_be_a_uuid():
    assert CorrectedClaimRequest(selections=[{"index": 0}]).risk_report_id is None
    report_id = uuid4()
    req = CorrectedClaimRequest(selections=[{"index": 0}], risk_report_id=str(report_id))
    assert req.risk_report_id == report_id
    with pytest.raises(ValidationError):
        CorrectedClaimRequest(selections=[{"index": 0}], risk_report_id="latest")
