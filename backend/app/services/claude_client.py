import json
import time
import uuid
from dataclasses import dataclass
from typing import TypeVar

import boto3
from botocore.config import Config
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import ModelRun
from app.services import s3

ModelT = TypeVar("ModelT", bound=BaseModel)

# Bedrock Messages API version constant (not the Heimdall app version).
ANTHROPIC_VERSION = "bedrock-2023-05-31"

_client = None


class ClaudeJSONError(Exception):
    """The model did not return valid JSON matching the schema after a retry."""


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
    case_id: uuid.UUID | None,
    purpose: str,
    prompt_version: str,
    call: _RawCall,
    status: str,
    error_message: str | None,
) -> tuple[str, str]:
    """Archive the raw request/response to S3 and write the model_runs row in its
    own committed transaction, so the audit/cost record survives even if the
    surrounding pipeline later fails and rolls back."""
    request_key = f"model_runs/{run_id}/request.json"
    response_key = f"model_runs/{run_id}/response.json"
    await run_in_threadpool(s3.put_text, request_key, json.dumps(call.request_body))
    await run_in_threadpool(s3.put_text, response_key, json.dumps(call.response_body))

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
            )
        )
        await session.commit()
    return request_key, response_key


async def complete_json(
    *,
    case_id: uuid.UUID | None,
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
    messages: list[dict] = [{"role": "user", "content": user_prompt}]

    for _ in range(2):
        call = await run_in_threadpool(_invoke, system, messages, max_tokens, temperature)
        run_id = uuid.uuid4()

        validated: ModelT | None = None
        error_message: str | None = None
        try:
            validated = schema.model_validate(_extract_json(call.text))
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            error_message = f"JSON parse/validation failed: {type(exc).__name__}"

        await _record_model_run(
            run_id,
            case_id=case_id,
            purpose=purpose,
            prompt_version=prompt_version,
            call=call,
            status="success" if validated is not None else "error",
            error_message=error_message,
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
