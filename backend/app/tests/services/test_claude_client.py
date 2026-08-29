"""complete_json — hard rules 6 and 7 live here and had no tests (MED-28).

Bedrock (`_invoke`), the DB session and the S3 archive are faked; what is pinned
is the contract: retry exactly once on bad JSON, a model_runs row for EVERY
call (success, parse failure, truncation, transport error), prompt_version and
input_truncated reaching the row, and no retry on a max_tokens stop.
"""

import uuid

import pytest
from pydantic import BaseModel, field_validator

from app.prompts.text import TRUNCATION_MARKER
from app.services import claude_client as cc

pytestmark = pytest.mark.asyncio


class Out(BaseModel):
    ok: bool


def _call(text: str, stop_reason: str = "end_turn") -> cc._RawCall:
    return cc._RawCall(
        text=text,
        input_tokens=10,
        output_tokens=5,
        latency_ms=1,
        stop_reason=stop_reason,
        request_body={},
        response_body={},
    )


class _Session:
    rows: list = []

    def add(self, row):
        _Session.rows.append(row)

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    _Session.rows = []
    monkeypatch.setattr(cc, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(cc.s3, "put_text", lambda *a, **k: None)
    yield


def _invoke_returning(*calls):
    it = iter(calls)

    def fake(system, messages, max_tokens, temperature):
        nxt = next(it)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    return fake


async def _run(monkeypatch, *calls, user_prompt="hello"):
    monkeypatch.setattr(cc, "_invoke", _invoke_returning(*calls))
    return await cc.complete_json(
        case_id=uuid.uuid4(),
        purpose="analysis",
        prompt_version="analyze_v5",
        system="sys",
        user_prompt=user_prompt,
        schema=Out,
    )


async def test_success_writes_one_row_with_prompt_version(monkeypatch):
    out = await _run(monkeypatch, _call('{"ok": true}'))
    assert out.data.ok is True
    assert [r.status for r in _Session.rows] == ["success"]
    assert _Session.rows[0].prompt_version == "analyze_v5"
    assert _Session.rows[0].input_truncated is False
    assert out.model_run_id == _Session.rows[0].id


async def test_bad_json_retries_exactly_once_and_records_both(monkeypatch):
    out = await _run(monkeypatch, _call("garbage"), _call('{"ok": false}'))
    assert out.data.ok is False
    assert [r.status for r in _Session.rows] == ["error", "success"]
    assert "JSON parse" in _Session.rows[0].error_message


async def test_two_bad_responses_fail_after_two_rows(monkeypatch):
    calls = [_call("nope"), _call("still nope"), _call('{"ok": true}')]  # third must never be used
    with pytest.raises(cc.ClaudeJSONError):
        await _run(monkeypatch, *calls)
    assert [r.status for r in _Session.rows] == ["error", "error"]


async def test_max_tokens_stop_does_not_retry(monkeypatch):
    with pytest.raises(cc.ClaudeTruncatedError):
        await _run(monkeypatch, _call("{", stop_reason="max_tokens"), _call('{"ok": true}'))
    assert len(_Session.rows) == 1 and _Session.rows[0].status == "error"
    assert "max_tokens" in _Session.rows[0].error_message


async def test_transport_error_records_a_row_then_propagates(monkeypatch):
    with pytest.raises(RuntimeError):
        await _run(monkeypatch, RuntimeError("throttled"))
    assert len(_Session.rows) == 1 and _Session.rows[0].status == "error"


async def test_truncated_prompt_is_recorded_on_the_row(monkeypatch):
    out = await _run(monkeypatch, _call('{"ok": true}'), user_prompt="note" + TRUNCATION_MARKER)
    assert out.data.ok
    assert _Session.rows[0].input_truncated is True


class _Picky(BaseModel):
    """A schema with the codebase's lenient-membership validator shape: `in`
    on a set raises TypeError (not ValidationError) for an unhashable value."""

    kind: str = "a"

    @field_validator("kind", mode="before")
    @classmethod
    def _member(cls, value: object) -> str:
        return value if value in {"a", "b"} else "a"


async def test_a_validator_crash_is_bad_output_not_a_lost_row(monkeypatch):
    # The model answered with a list where a string was due. The Bedrock call
    # happened, so the row must be written (rule 7) and the one retry must
    # fire (rule 6) — whatever exception class the validator raised.
    monkeypatch.setattr(
        cc, "_invoke", _invoke_returning(_call('{"kind": ["a"]}'), _call('{"kind": "b"}'))
    )
    out = await cc.complete_json(
        case_id=uuid.uuid4(),
        purpose="analysis",
        prompt_version="analyze_v5",
        system="sys",
        user_prompt="hello",
        schema=_Picky,
    )
    assert out.data.kind == "b"
    assert [r.status for r in _Session.rows] == ["error", "success"]
    assert _Session.rows[0].error_message == "JSON parse/validation failed: TypeError"
