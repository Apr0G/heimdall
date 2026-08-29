import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TypeVar

import boto3
from botocore.config import Config
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import ModelRun
from app.prompts.text import was_truncated
from app.services import s3

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

# Bedrock Messages API version constant (not the Heimdall app version).
ANTHROPIC_VERSION = "bedrock-2023-05-31"

_client = None


class ClaudeJSONError(Exception):
    """The model did not return valid JSON matching the schema after a retry."""


class ClaudeTruncatedError(Exception):
    """The model hit max_tokens mid-response. Retrying the identical prompt would
    truncate identically, so this is deliberately NOT retried — it is a capacity
    problem (prompt or max_tokens), not a formatting one."""


def _bedrock():
    global _client
    if _client is None:
        # Default botocore read timeout is 60s — a multi-thousand-token letter draft
        # at low throughput can exceed it and error a case the model would finish.
        # Adaptive retries add throttling backoff (client-side retry loop only
        # handles bad JSON, not Bedrock TPS limits).
        _client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=Config(
                connect_timeout=10,
                read_timeout=300,
                retries={"max_attempts": 4, "mode": "adaptive"},
            ),
        )
    return _client


@dataclass
class _RawCall:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    stop_reason: str
    request_body: dict
    response_body: dict


@dataclass
class ModelOutcome:
    data: BaseModel
    model_run_id: uuid.UUID
    input_tokens: int
    output_tokens: int


def _invoke(system: str, messages: list[dict], max_tokens: int, temperature: float) -> _RawCall:
    """One synchronous Bedrock invoke_model call (run via threadpool)."""
    body = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": messages,
    }
    start = time.perf_counter()
    response = _bedrock().invoke_model(modelId=settings.bedrock_model_id, body=json.dumps(body))
    latency_ms = int((time.perf_counter() - start) * 1000)
    payload = json.loads(response["body"].read())
    text = "".join(
        block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
    )
    usage = payload.get("usage", {})
    return _RawCall(
        text=text,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        latency_ms=latency_ms,
        stop_reason=payload.get("stop_reason", ""),
        request_body=body,
        response_body=payload,
    )


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of the response, tolerating fences/preamble."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


async def _record_model_run(
    run_id: uuid.UUID,
    *,
    case_id: uuid.UUID,
    purpose: str,
    prompt_version: str,
    call: _RawCall,
    status: str,
    error_message: str | None,
    input_truncated: bool = False,
) -> tuple[str, str]:
    """Write the model_runs row, then archive the raw request/response to S3.

    Order matters (hard rule 7): the row is the billing and training record, so it
    is committed FIRST with pre-computed S3 keys. If the archive upload then fails,
    we lose the raw payload for a call we still paid for — recoverable. The old
    order lost the row itself, which is not. The row commits in its own transaction
    so it survives a later rollback of the surrounding pipeline."""
    request_key = f"model_runs/{run_id}/request.json"
    response_key = f"model_runs/{run_id}/response.json"

    async with AsyncSessionLocal() as session:
        session.add(
            ModelRun(
                id=run_id,
                case_id=case_id,
                purpose=purpose,
                provider="bedrock",
                model_id=settings.bedrock_model_id,
                prompt_version=prompt_version,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                latency_ms=call.latency_ms,
                raw_request_s3_key=request_key,
                raw_response_s3_key=response_key,
                status=status,
                error_message=error_message,
                input_truncated=input_truncated,
            )
        )
        await session.commit()

    # The row is committed; the archive is best-effort. Failing the case here
    # would throw away a validated, billed result over a raw-payload copy.
    try:
        await run_in_threadpool(s3.put_text, request_key, json.dumps(call.request_body))
        await run_in_threadpool(s3.put_text, response_key, json.dumps(call.response_body))
    except Exception as exc:  # noqa: BLE001 — any S3 failure; logged, never fatal
        logger.warning(
            "model_run archive upload failed",
            extra={"context": {"model_run_id": str(run_id), "error": type(exc).__name__}},
        )
        async with AsyncSessionLocal() as session:
            row = await session.get(ModelRun, run_id)
            if row is not None:
                row.error_message = (
                    row.error_message + "; " if row.error_message else ""
                ) + f"archive upload failed ({type(exc).__name__})"
                await session.commit()
    return request_key, response_key


async def _record_invoke_error(
    run_id: uuid.UUID,
    *,
    case_id: uuid.UUID,
    purpose: str,
    prompt_version: str,
    error_message: str,
) -> None:
    """Record a model_runs row for a Bedrock call that failed at the transport
    layer (throttle exhausted, timeout) before any response — hard rule 6 requires
    a row for *every* call, and this is exactly when cost/failure telemetry matters.
    No S3 archives: there is no response, and the prompt is re-derivable."""
    async with AsyncSessionLocal() as session:
        session.add(
            ModelRun(
                id=run_id,
                case_id=case_id,
                purpose=purpose,
                provider="bedrock",
                model_id=settings.bedrock_model_id,
                prompt_version=prompt_version,
                status="error",
                error_message=error_message,
            )
        )
        await session.commit()


def _invoke_error_message(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    return f"invoke failed: {type(exc).__name__}" + (f" ({code})" if code else "")


async def complete_json(
    *,
    case_id: uuid.UUID,
    purpose: str,
    prompt_version: str,
    system: str,
    user_prompt: str,
    schema: type[ModelT],
    max_tokens: int = 2000,
    temperature: float = 0.0,
) -> ModelOutcome:
    """Force a JSON response from Claude on Bedrock, validate it against `schema`,
    retrying once with a corrective turn on parse/validation failure. Every
    Bedrock call writes a model_runs row. Raises ClaudeJSONError if both fail."""
    # Recorded on every row this call writes (rule 9: a silently shortened
    # clinical note must leave a trace somewhere other than inside the prompt).
    input_truncated = was_truncated(system, user_prompt)
    if input_truncated:
        logger.warning(
            "prompt input truncated",
            extra={"context": {"case_id": str(case_id), "purpose": purpose}},
        )

    messages: list[dict] = [{"role": "user", "content": user_prompt}]

    for _ in range(2):
        run_id = uuid.uuid4()
        try:
            call = await run_in_threadpool(_invoke, system, messages, max_tokens, temperature)
        except Exception as exc:
            # Transport-layer failure (throttle/timeout): record an error row so the
            # call is still accounted for (rule 6), then propagate.
            await _record_invoke_error(
                run_id,
                case_id=case_id,
                purpose=purpose,
                prompt_version=prompt_version,
                error_message=_invoke_error_message(exc),
            )
            raise

        # A max_tokens stop is a truncated response, not malformed output. The retry
        # sends the same prompt with the same ceiling, so it truncates again and the
        # case reports "invalid JSON" having burned two full calls. Fail loudly and
        # distinctly instead, and record the row before propagating.
        if call.stop_reason == "max_tokens":
            await _record_model_run(
                run_id,
                case_id=case_id,
                purpose=purpose,
                prompt_version=prompt_version,
                call=call,
                status="error",
                error_message=f"response truncated at max_tokens={max_tokens}",
                input_truncated=input_truncated,
            )
            raise ClaudeTruncatedError(
                f"{purpose}: model response hit the {max_tokens}-token ceiling"
            )

        validated: ModelT | None = None
        error_message: str | None = None
        try:
            validated = schema.model_validate(_extract_json(call.text))
        except Exception as exc:  # noqa: BLE001 — see below
            # Anything the parse or a validator raises is "bad output": a
            # ValidationError, but also a TypeError from a lenient validator
            # handed a list where a string was due. The Bedrock call already
            # happened, so the row (rule 7) and the single retry (rule 6) must
            # not depend on which exception class a validator happened to use.
            # Type name only — the message can echo document text.
            error_message = f"JSON parse/validation failed: {type(exc).__name__}"

        await _record_model_run(
            run_id,
            case_id=case_id,
            purpose=purpose,
            prompt_version=prompt_version,
            call=call,
            status="success" if validated is not None else "error",
            error_message=error_message,
            input_truncated=input_truncated,
        )

        if validated is not None:
            return ModelOutcome(
                data=validated,
                model_run_id=run_id,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
            )

        # Retry once with the model's bad output and an explicit correction.
        messages = [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": call.text},
            {
                "role": "user",
                "content": (
                    "Your last response was not valid JSON for the required schema. "
                    "Return ONLY the JSON object — no markdown fences, no preamble."
                ),
            },
        ]

    raise ClaudeJSONError(f"{purpose}: model did not return valid JSON after retry")
