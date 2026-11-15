"""The only route to any model. Prompts and answers are never logged or traced."""

import json
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import httpx

from job_copilot.db import EVAL_USER_ID, SEEDED_USER_ID, connect

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


HAIKU = "anthropic/claude-haiku-5-5"
GROQ_PERSONAL = "groq/openai/gpt-oss-120b"
CLOUDFLARE_PERSONAL = "cloudflare/@cf/openai/gpt-oss-120b"
BOTH = frozenset({DataClass.POSTING, DataClass.PERSONAL})

# Only models listed here can be called. Re-check prices and terms before adding one. Personal
# data goes only to models whose terms rule out training on it: never add one that may train.
MODELS = {
    "groq/openai/gpt-oss-20b": ModelRule(frozenset({DataClass.POSTING})),
    "cloudflare/@cf/openai/gpt-oss-20b": ModelRule(frozenset({DataClass.POSTING})),
    HAIKU: ModelRule(BOTH, Decimal("0.10"), Decimal("0.50")),
    # Groq production models with Zero Data Retention on, which the person confirms on Settings.
    GROQ_PERSONAL: ModelRule(BOTH),
    # Plain Workers AI inference, never through Cloudflare AI Gateway, which can log requests.
    CLOUDFLARE_PERSONAL: ModelRule(BOTH),
}

# Fallback Lists: each step tries these in order and uses the first that can take the call.
PERSONAL_MODELS = (HAIKU, GROQ_PERSONAL, CLOUDFLARE_PERSONAL)
POSTING_MODELS = ("groq/openai/gpt-oss-20b", "cloudflare/@cf/openai/gpt-oss-20b")

# The settings each provider needs; a provider without them is skipped.
PROVIDER_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "cloudflare": ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_KEY"),
}


class GatewayError(Exception):
    """Messages never contain prompt or answer text."""


class NotEligible(GatewayError):
    pass


class CapReached(GatewayError):
    pass


class ModelUnavailable(GatewayError):
    def __init__(self, message: str, out_of_credit: bool = False) -> None:
        super().__init__(message)
        # The provider refused the key or the account has no credit, so retrying won't help today.
        self.out_of_credit = out_of_credit


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
    model: str


def strip_fences(answer: str) -> str:
    """Models sometimes wrap JSON in a Markdown code fence."""
    return answer.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def parse_json(answer: str) -> Any:
    """The JSON value in a model's answer, ignoring a code fence or stray text around it."""
    text = strip_fences(answer)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        if not starts:
            raise
        return json.JSONDecoder().raw_decode(text, min(starts))[0]


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
    options: dict[str, Any] = {}
    if model.startswith("cloudflare/"):
        # Workers AI's OpenAI-compatible endpoint.
        # ponytail: unverified until a Cloudflare key is first used; check it with live_check.
        account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
        model = "openai/" + model.removeprefix("cloudflare/")
        options = {
            "api_base": f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1",
            "api_key": os.environ["CLOUDFLARE_API_KEY"],
        }
    response: Any = litellm.completion(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        timeout=CALL_TIMEOUT_SECONDS,
        **options,
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


# The start of this calendar month in UTC, when every cap starts again.
MONTH_START = "date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"


def spenders(user_id: UUID) -> tuple[UUID, ...]:
    """Whose paid calls count towards a person's cap: the owner's covers evals too."""
    # ponytail: one owner in local mode; evals belong to whoever owns the install.
    return (user_id, EVAL_USER_ID) if user_id == SEEDED_USER_ID else (user_id,)


def caps_for(user_id: UUID) -> tuple[UUID, ...]:
    """Each cap a person's paid call counts against: an eval call is held to evals' own cap
    first, and to the owner's."""
    return (EVAL_USER_ID, SEEDED_USER_ID) if user_id == EVAL_USER_ID else (user_id,)


def cap_and_spent(conn: Any, user_id: UUID) -> tuple[Decimal, Decimal]:
    """A person's monthly cap, and this month's spending towards it."""
    row: Any = conn.execute(
        f"""SELECT u.monthly_cap_usd AS cap,
                   (SELECT COALESCE(SUM(c.cost_usd), 0) FROM model_calls c
                    WHERE c.user_id = ANY(%s) AND c.created_at >= {MONTH_START}) AS spent
            FROM users u WHERE u.id = %s""",
        (list(spenders(user_id)), user_id),
    ).fetchone()
    return Decimal(row["cap"]), Decimal(row["spent"])


def _check_cap(
    user_id: UUID, rule: ModelRule, messages: list[dict[str, str]], max_output_tokens: int
) -> None:
    chars = sum(len(message["content"]) for message in messages)
    estimate = _cost(rule, chars // CHARS_PER_TOKEN_ESTIMATE + 1, max_output_tokens)
    # ponytail: check then call, so parallel workers could overshoot slightly; reserve spend
    # in a transaction if more than one worker runs paid calls for a user.
    with connect() as conn:
        for cap_owner in caps_for(user_id):
            cap, spent = cap_and_spent(conn, cap_owner)
            if spent + estimate > cap:
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
    application_id: UUID | None = None,
) -> Completion:
    rule = MODELS.get(model)
    if rule is None or data_class not in rule.data_classes:
        raise NotEligible(f"{model} may not receive {data_class.value} data")
    if rule.input_usd_per_million or rule.output_usd_per_million:
        _check_cap(user_id, rule, messages, max_output_tokens)

    started = time.monotonic()
    failure = ""
    out_of_credit = False
    try:
        answer = call_provider(model, messages, max_output_tokens)
    except Exception as error:
        failure = type(error).__name__
        # Read here and never kept: provider errors can quote the request.
        out_of_credit = failure == "AuthenticationError" or "credit balance" in str(error).lower()
    if failure:
        # Provider errors can quote the request, so only the error's type goes any further.
        # Raising out here keeps the original error off this exception's context too.
        log.warning("Model call failed: step=%s model=%s %s", step, model, failure)
        raise ModelUnavailable(f"{model} failed: {failure}", out_of_credit)

    cost = _cost(rule, answer.input_tokens, answer.output_tokens)
    settings = trace_settings()
    # A failed send may still have been delivered, so the ID is kept for later deletion.
    trace_id = uuid4().hex if settings else None
    with connect() as conn:
        conn.execute(
            """INSERT INTO model_calls (user_id, model, step, input_tokens, output_tokens,
                                        cost_usd, trace_id, application_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                user_id,
                model,
                step,
                answer.input_tokens,
                answer.output_tokens,
                cost,
                trace_id,
                application_id,
            ),
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
    return Completion(answer.text, cost, trace_id, model)


NO_CREDIT = (
    "Anthropic didn't accept your key or your account is out of credit, so free models that "
    "don't train on your data are in use until tomorrow."
)


def settings_owner(user_id: UUID) -> UUID:
    """Whose keys and model settings a call uses: evals use the owner's."""
    return SEEDED_USER_ID if user_id == EVAL_USER_ID else user_id


def has_keys(model: str) -> bool:
    provider = model.split("/", 1)[0]
    return all(os.environ.get(name) for name in PROVIDER_KEYS[provider])


def _is_paid(model: str) -> bool:
    rule = MODELS[model]
    return bool(rule.input_usd_per_million or rule.output_usd_per_million)


def model_settings(user_id: UUID) -> Any:
    """Whether Groq's Zero Data Retention is confirmed, and until when paid models are out."""
    with connect() as conn:
        return conn.execute(
            """SELECT groq_zdr_confirmed, paid_unavailable_until, paid_unavailable_reason
               FROM users WHERE id = %s""",
            (settings_owner(user_id),),
        ).fetchone()


def _skip(model: str, data_class: DataClass, settings: Any) -> bool:
    if not has_keys(model):
        return True
    if model.startswith("groq/") and data_class is DataClass.PERSONAL:
        return not settings["groq_zdr_confirmed"]
    until = settings["paid_unavailable_until"]
    return _is_paid(model) and until is not None and until > datetime.now(UTC)


def _paid_out_until_tomorrow(user_id: UUID) -> None:
    tomorrow = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        days=1
    )
    with connect() as conn:
        conn.execute(
            """UPDATE users SET paid_unavailable_until = %s, paid_unavailable_reason = %s
               WHERE id = %s""",
            (tomorrow, NO_CREDIT, settings_owner(user_id)),
        )


def complete_first(
    *,
    user_id: UUID,
    models: Sequence[str],
    data_class: DataClass,
    step: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
    application_id: UUID | None = None,
) -> Completion:
    """Call the first model on a Fallback List that can take the call.

    A model is passed over without its keys, for Groq with personal data until Zero Data
    Retention is confirmed, and for a paid model at the cap or when its credit ran out today.
    Eval Cases stop at their own cap instead, so they never test a model the person isn't using.
    """
    for model in models:
        rule = MODELS.get(model)
        if rule is None or data_class not in rule.data_classes:
            raise NotEligible(f"{model} may not receive {data_class.value} data")
    settings = model_settings(user_id)
    failures: list[str] = []
    for model in models:
        if _skip(model, data_class, settings):
            continue
        try:
            return complete(
                user_id=user_id,
                model=model,
                data_class=data_class,
                step=step,
                messages=messages,
                max_output_tokens=max_output_tokens,
                application_id=application_id,
            )
        except CapReached:
            if user_id == EVAL_USER_ID:
                raise
            failures.append(f"{model}: monthly cap reached")
        except ModelUnavailable as error:
            if error.out_of_credit and _is_paid(model):
                _paid_out_until_tomorrow(user_id)
            failures.append(str(error))
    raise ModelUnavailable("; ".join(failures) or "No model is set up for this step")
