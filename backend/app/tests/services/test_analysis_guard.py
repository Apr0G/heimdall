"""The never-appeal override inside run_ai_analysis — the CONSUMER of
never_appealable_codes. The helper alone being correct proves nothing if the
`and not blocking_codes` conjunct is ever removed (MED-29)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.analysis import AnalysisResult
from app.services import analysis as svc

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self, extraction):
        self.extraction = extraction
        self.added = []

    async def scalar(self, stmt):
        return self.extraction

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


def _extraction(carc, group):
    return SimpleNamespace(carc_codes=carc, group_codes=group, extracted_json={})


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    monkeypatch.setattr(svc, "read_clinical_text", AsyncMock(return_value="note"))
    monkeypatch.setattr(svc, "read_supplemental_text", AsyncMock(return_value=""))


def _model_says(monkeypatch, appealable: bool):
    result = AnalysisResult.model_validate(
        {
            "is_appealable": appealable,
            "appealability_reason": "model says so",
            "success_probability": 0.8,
            "denial_category": "other",
        }
    )
    outcome = MagicMock(data=result, model_run_id=uuid.uuid4())
    monkeypatch.setattr(svc.claude_client, "complete_json", AsyncMock(return_value=outcome))


async def _run(monkeypatch, carc, group, appealable=True):
    _model_says(monkeypatch, appealable)
    session = FakeSession(_extraction(carc, group))
    case = SimpleNamespace(id=uuid.uuid4(), practice_id=uuid.uuid4())
    analysis = await svc.run_ai_analysis(session, case)
    return analysis


async def test_pr_code_overrides_model_even_when_split_or_misspelled(monkeypatch):
    for carc, group in ((["PR-1"], []), (["PR 1"], []), (["1"], ["PR"])):
        analysis = await _run(monkeypatch, carc, group, appealable=True)
        assert analysis.is_appealable is False, (carc, group)
        assert "overridden" in analysis.appealability_reason


async def test_appealable_code_keeps_model_verdict(monkeypatch):
    analysis = await _run(monkeypatch, ["CO-50"], ["CO"], appealable=True)
    assert analysis.is_appealable is True
    assert analysis.appealability_reason == "model says so"


async def test_model_not_appealable_is_never_flipped_to_appealable(monkeypatch):
    analysis = await _run(monkeypatch, ["CO-50"], ["CO"], appealable=False)
    assert analysis.is_appealable is False
