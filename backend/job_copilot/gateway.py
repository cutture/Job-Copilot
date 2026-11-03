"""The only route to any model. Prompts and answers are never logged or traced."""

import json
import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import httpx

from job_copilot.db import connect

log = logging.getLogger(__name__)

CALL_TIMEOUT_SECONDS = 60
TRACE_TIMEOUT_SECONDS = 5
PER_TOKEN = Decimal("0.000001")
CHARS_PER_TOKEN_ESTIMATE = 3
NOT_RECORDED = "Not recorded: Job Copilot never sends prompt or answer text"


class DataClass(Enum):
    POSTING = "posting"
    PERSONAL = "personal"


@dataclass(frozen=True)
class ModelRule:
    data_classes: frozenset[DataClass]
    input_usd_per_million: Decimal = Decimal(0)
    output_usd_per_million: Decimal = Decimal(0)


# Only models listed here can be called. Re-check prices and terms before adding one.
MODELS = {
    "groq/openai/gpt-oss-20b": ModelRule(frozenset({DataClass.POSTING})),
    "anthropic/claude-haiku-5-5": ModelRule(
        frozenset({DataClass.POSTING, DataClass.PERSONAL}), Decimal("0.10"), Decimal("0.50")
    ),
}


class GatewayError(Exception):
    """Messages never contain prompt or answer text."""


class NotEligible(GatewayError):
    pass


class CapReached(GatewayError):
    pass


class ModelUnavailable(GatewayError):
    pass


@dataclass(frozen=True)
class ProviderAnswer:
    text: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Completion:
    text: str
    cost_usd: Decimal
    trace_id: str | None


def strip_fences(answer: str) -> str:
    """Models sometimes wrap JSON in a Markdown code fence."""
    return answer.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


@dataclass(frozen=True)
class TraceSettings:
    public_key: str
    secret_key: str
    host: str


def call_provider(model: str, messages: list[dict[str, str]], max_tokens: int) -> ProviderAnswer:
    import litellm

    litellm.suppress_debug_info = True
    litellm.telemetry = False
    logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
    response: Any = litellm.completion(
        model=model, messages=messages, max_tokens=max_tokens, timeout=CALL_TIMEOUT_SECONDS
    )
    return ProviderAnswer(
        response.choices[0].message.content or "",
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )


def trace_settings() -> TraceSettings | None:
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST")
    if not (public_key and secret_key):
        return None
    if not host:
        log.warning("Tracing is off: set LANGFUSE_HOST to the data region you chose")
        return None
    return TraceSettings(public_key, secret_key, host)


def send_trace(settings: TraceSettings, event: dict[str, Any]) -> None:
    """Send one model call to Langfuse as an OpenTelemetry generation, with metadata only.

    Leaving out prompts and answers is the masking.
    """
    end_ns = time.time_ns()
    start_ns = end_ns - round(float(event["seconds"]) * 1_000_000_000)
    attributes = {
        "langfuse.observation.type": "generation",
        "langfuse.observation.model.name": event["model"],
        "langfuse.observation.usage_details": json.dumps(
            {"input": event["input_tokens"], "output": event["output_tokens"]}
        ),
        "langfuse.observation.cost_details": json.dumps({"total": float(event["cost_usd"])}),
        "langfuse.observation.input": json.dumps(NOT_RECORDED),
        "langfuse.observation.output": json.dumps(NOT_RECORDED),
        "langfuse.trace.name": event["step"],
        "langfuse.user.id": event["user_id"],
    }
    span = {
        "traceId": event["trace_id"],
        "spanId": uuid4().hex[:16],
        "name": event["step"],
        "kind": 1,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [
            {"key": key, "value": {"stringValue": str(value)}} for key, value in attributes.items()
        ],
    }
    body = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "job-copilot"}}]
                },
                "scopeSpans": [{"scope": {"name": "job-copilot"}, "spans": [span]}],
            }
        ]
    }
    httpx.post(
        f"{settings.host.rstrip('/')}/api/public/otel/v1/traces",
        json=body,
        auth=(settings.public_key, settings.secret_key),
        # Without this header, Langfuse can take up to 10 minutes to show the data.
        headers={"x-langfuse-ingestion-version": "4"},
        timeout=TRACE_TIMEOUT_SECONDS,
    ).raise_for_status()


def _cost(rule: ModelRule, input_tokens: int, output_tokens: int) -> Decimal:
    return PER_TOKEN * (
        input_tokens * rule.input_usd_per_million + output_tokens * rule.output_usd_per_million
    )


def _check_cap(
    user_id: UUID, rule: ModelRule, messages: list[dict[str, str]], max_output_tokens: int
) -> None:
    chars = sum(len(message["content"]) for message in messages)
    estimate = _cost(rule, chars // CHARS_PER_TOKEN_ESTIMATE + 1, max_output_tokens)
    # ponytail: check then call, so parallel workers could overshoot slightly; reserve spend
    # in a transaction if more than one worker runs paid calls for a user.
    with connect() as conn:
        row: Any = conn.execute(
            """SELECT u.monthly_cap_usd AS cap, COALESCE(SUM(c.cost_usd), 0) AS spent
               FROM users u LEFT JOIN model_calls c ON c.user_id = u.id
                 AND c.created_at >=
                     date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
               WHERE u.id = %s GROUP BY u.monthly_cap_usd""",
            (user_id,),
        ).fetchone()
    if row["spent"] + estimate > row["cap"]:
        raise CapReached("The monthly paid API cap has been reached")


def _trace(settings: TraceSettings, event: dict[str, Any]) -> None:
    try:
        send_trace(settings, event)
    except Exception as error:  # Tracing must never lose an answer that was paid for.
        log.warning("Trace not sent: %s", type(error).__name__)


def complete(
    *,
    user_id: UUID,
    model: str,
    data_class: DataClass,
    step: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
) -> Completion:
    rule = MODELS.get(model)
    if rule is None or data_class not in rule.data_classes:
        raise NotEligible(f"{model} may not receive {data_class.value} data")
    if rule.input_usd_per_million or rule.output_usd_per_million:
        _check_cap(user_id, rule, messages, max_output_tokens)

    started = time.monotonic()
    failure = ""
    try:
        answer = call_provider(model, messages, max_output_tokens)
    except Exception as error:
        failure = type(error).__name__
    if failure:
        # Provider errors can quote the request, so only the error's type goes any further.
        # Raising out here keeps the original error off this exception's context too.
        log.warning("Model call failed: step=%s model=%s %s", step, model, failure)
        raise ModelUnavailable(f"{model} failed: {failure}")

    cost = _cost(rule, answer.input_tokens, answer.output_tokens)
    settings = trace_settings()
    # A failed send may still have been delivered, so the ID is kept for later deletion.
    trace_id = uuid4().hex if settings else None
    with connect() as conn:
        conn.execute(
            """INSERT INTO model_calls
               (user_id, model, step, input_tokens, output_tokens, cost_usd, trace_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, model, step, answer.input_tokens, answer.output_tokens, cost, trace_id),
        )
    if settings:
        _trace(
            settings,
            {
                "trace_id": trace_id,
                "user_id": str(user_id),
                "step": step,
                "model": model,
                "input_tokens": answer.input_tokens,
                "output_tokens": answer.output_tokens,
                "cost_usd": str(cost),
                "seconds": round(time.monotonic() - started, 3),
            },
        )
    log.info("Model call done: step=%s model=%s trace=%s", step, model, trace_id)
    return Completion(answer.text, cost, trace_id)
