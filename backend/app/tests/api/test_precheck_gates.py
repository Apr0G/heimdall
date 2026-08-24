"""Pre-check case-type gates in the cases router (pure helpers — no DB/HTTP).

The document-set rule and the appeal-only endpoint gates are the two controls
that keep the pre-check flow inside its lane; both are exact and unit-testable.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.cases import _pipeline_for, _require_appeal_case, _require_docs
from app.services.pipeline import run_full_pipeline, run_precheck_pipeline


class TestRequireDocs:
    def test_appeal_requires_exactly_the_triad(self):
        _require_docs("appeal", ["denial", "claim", "clinical"])
        _require_docs("appeal", ["clinical", "denial", "claim"])  # order-free

    def test_pre_check_requires_exactly_claim_and_clinical(self):
        _require_docs("pre_check", ["claim", "clinical"])
        _require_docs("pre_check", ["clinical", "claim"])

    @pytest.mark.parametrize(
        ("case_type", "doc_types"),
        [
            ("appeal", ["claim", "clinical"]),  # pre-check set on an appeal
            ("pre_check", ["denial", "claim", "clinical"]),  # triad on a pre-check
            ("pre_check", ["claim"]),  # missing clinical
            ("pre_check", ["claim", "claim"]),  # duplicate type
            ("pre_check", ["claim", "clinical", "clinical"]),
            ("appeal", []),
            ("pre_check", []),
        ],
    )
    def test_wrong_sets_rejected(self, case_type, doc_types):
        with pytest.raises(HTTPException) as exc:
            _require_docs(case_type, doc_types)
        assert exc.value.status_code == 400


class TestAppealOnlyGate:
    def test_appeal_passes(self):
        _require_appeal_case(SimpleNamespace(case_type="appeal"))

    def test_pre_check_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _require_appeal_case(SimpleNamespace(case_type="pre_check"))
        assert exc.value.status_code == 400


class TestPipelineDispatch:
    def test_by_case_type(self):
        assert _pipeline_for("appeal") is run_full_pipeline
        assert _pipeline_for("pre_check") is run_precheck_pipeline
