"""The only route to any model. Prompts and answers are never logged or traced."""

import json
import logging
import os
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, NamedTuple
from uuid import UUID, uuid4

import httpx

from job_copilot.db import EVAL_USER_ID, SEEDED_USER_ID, connect

log = logging.getLogger(__name__)

CALL_TIMEOUT_SECONDS = 60
TRACE_TIMEOUT_SECONDS = 5
PER_TOKEN = Decimal("0.000001")
CHARS_PER_TOKEN_ESTIMATE = 3
NOT_RECORDED = "Not recorded: Job Copilot never sends prompt or answer text"
# Free tiers limit tokens per minute, so a rate-limited model is asked again after waiting,
# across about a minute, before the next model on the list.
RATE_LIMIT_TRIES = 3
# A model step pauses after its whole Fallback List fails this many times in a row, for a while.
PAUSE_AFTER_FAILURES = 3
PAUSE_MINUTES = 30
RATE_LIMIT_WAIT_SECONDS = 30.0


class DataClass(Enum):
    POSTING = "posting"
    PERSONAL = "personal"


@dataclass(frozen=True)
class ModelRule:
    data_classes: frozenset[DataClass]
    input_usd_per_million: Decimal = Decimal(0)
    output_usd_per_million: Decimal = Decimal(0)


HAIKU = "anthropic/claude-haiku-5-5"
SONNET = "anthropic/claude-sonnet-5-5"
GROQ_PERSONAL = "groq/openai/gpt-oss-120b"
CLOUDFLARE_PERSONAL = "cloudflare/@cf/openai/gpt-oss-120b"
POSTING_AND_PERSONAL = frozenset({DataClass.POSTING, DataClass.PERSONAL})

# Only models listed here can be called. Re-check prices and terms before adding one. Personal
# data goes only to models whose terms rule out training on it: never add one that may train.
MODELS = {
    "groq/openai/gpt-oss-20b": ModelRule(frozenset({DataClass.POSTING})),
    "cloudflare/@cf/openai/gpt-oss-20b": ModelRule(frozenset({DataClass.POSTING})),
    HAIKU: ModelRule(POSTING_AND_PERSONAL, Decimal("0.10"), Decimal("0.50")),
    # A Challenger the owner runs by hand: 20 times Haiku's price.
    SONNET: ModelRule(POSTING_AND_PERSONAL, Decimal("2.00"), Decimal("10.00")),
    # Groq production models with Zero Data Retention on, which the person confirms on Settings.
    GROQ_PERSONAL: ModelRule(POSTING_AND_PERSONAL),
    # Plain Workers AI inference, never through Cloudflare AI Gateway, which can log requests.
    CLOUDFLARE_PERSONAL: ModelRule(POSTING_AND_PERSONAL),
}

# How a model is named to the person, on a Pack and the Eval Runs page.
MODEL_NAMES = {
    "groq/openai/gpt-oss-20b": "Groq gpt-oss-20b (free)",
    "cloudflare/@cf/openai/gpt-oss-20b": "Cloudflare gpt-oss-20b (free)",
    HAIKU: "Claude Haiku 5.5",
    SONNET: "Claude Sonnet 5.5",
    GROQ_PERSONAL: "Groq gpt-oss-120b (free)",
    CLOUDFLARE_PERSONAL: "Cloudflare gpt-oss-120b (free)",
}

# Fallback Lists: each step tries these in order and uses the first that can take the call.
PERSONAL_MODELS = (HAIKU, GROQ_PERSONAL, CLOUDFLARE_PERSONAL)
POSTING_MODELS = ("groq/openai/gpt-oss-20b", "cloudflare/@cf/openai/gpt-oss-20b")

# Which model step each call belongs to: a step's model is approved, and challenged, as one.
STEP_OF = {
    "filter": "filter",
    "resume_evidence": "evidence",
    "rating": "rating",
    # A Rescore judges with the rating's model.
    "rescore": "rating",
    "pack_resume": "pack",
    "pack_cover_letter": "pack",
    # Form answers are written like the Pack, by its model.
    "form_answers": "pack",
    "pack_verification": "verification",
    # Check again on one Removed Claim: Verification's model, counted apart from writing Packs.
    "pack_check_again": "verification",
}

# How each model step is named to the person.
STEP_LABELS = {
    "filter": "Filter",
    "evidence": "Reading the resume",
    "rating": "Rating Matches",
    "pack": "Writing Application Packs",
    "verification": "Verification",
}


class Challenger(NamedTuple):
    """A model tried on one model step."""

    step: str
    model: str


# The model steps each kind of queued job calls, so a paused step's jobs wait.
JOB_STEPS = {
    "process_posting": ["filter"],
    "extract_evidence": ["evidence"],
    "rate_match": ["rating"],
    "generate_pack": ["pack", "verification"],
    "rescore_match": ["rating"],
}

# The Challenger a run is trying; calls for its step use it alone.
_challenger: ContextVar[Challenger | None] = ContextVar("challenger", default=None)
# Where calls record the model each step used, while an Eval Case runs.
_used: ContextVar[dict[str, str] | None] = ContextVar("used", default=None)


@contextmanager
def challenging(challenger: Challenger) -> Iterator[None]:
    """Run one step on one model, with no Fallback List, as a Challenger run does."""
    token = _challenger.set(challenger)
    try:
        yield
    finally:
        _challenger.reset(token)


def active_challenger() -> Challenger | None:
    return _challenger.get()


@contextmanager
def recording_models() -> Iterator[dict[str, str]]:
    """Record the model each step used for the calls made inside."""
    used: dict[str, str] = {}
    token = _used.set(used)
    try:
        yield used
    finally:
        _used.reset(token)


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
    def __init__(
        self, message: str, out_of_credit: bool = False, rate_limited: bool = False
    ) -> None:
        super().__init__(message)
        # The provider refused the key or the account has no credit, so retrying won't help today.
        self.out_of_credit = out_of_credit
        self.rate_limited = rate_limited


class StepPaused(ModelUnavailable):
    """The model step failed too often in a row, so it waits a while before trying again."""


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


def price_of(rule: ModelRule, input_tokens: int, output_tokens: int) -> Decimal:
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
    estimate = price_of(rule, chars // CHARS_PER_TOKEN_ESTIMATE + 1, max_output_tokens)
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
        out_of_credit = (
            failure in ("AuthenticationError", "PermissionDeniedError")
            or "credit balance" in str(error).lower()
        )
    if failure:
        # Provider errors can quote the request, so only the error's type goes any further.
        # Raising out here keeps the original error off this exception's context too.
        log.warning("Model call failed: step=%s model=%s %s", step, model, failure)
        raise ModelUnavailable(
            f"{model} failed: {failure}", out_of_credit, rate_limited=failure == "RateLimitError"
        )

    cost = price_of(rule, answer.input_tokens, answer.output_tokens)
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


FREE_IN_USE = "free models that don't train on your data are in use"
NO_KEY = (
    f"No Anthropic key is set, so {FREE_IN_USE}. To use Claude Haiku, add ANTHROPIC_API_KEY "
    "to your .env file and restart the app."
)
NO_CREDIT = (
    f"Anthropic didn't accept your key or your account is out of credit, so {FREE_IN_USE} "
    "until tomorrow. Add credit or check your key in the Anthropic Console."
)
AT_CAP = (
    f"You've reached this month's cap, so {FREE_IN_USE} until the 1st. Raise the cap above "
    "to use Claude Haiku again."
)


@dataclass(frozen=True)
class ModelStatus:
    paid: bool
    # Why free models are in use, and what to do about it, when they are.
    note: str | None
    groq_zdr_confirmed: bool
    # Free models are in use and none may receive personal data yet.
    personal_work_waits: bool


def model_name(model: str) -> str:
    return MODEL_NAMES.get(model, model)


def settings_owner(user_id: UUID) -> UUID:
    """Whose keys and model settings a call uses: evals use the owner's."""
    return SEEDED_USER_ID if user_id == EVAL_USER_ID else user_id


def has_keys(model: str) -> bool:
    provider = model.split("/", 1)[0]
    return all(os.environ.get(name) for name in PROVIDER_KEYS[provider])


def _is_paid(model: str) -> bool:
    rule = MODELS[model]
    return bool(rule.input_usd_per_million or rule.output_usd_per_million)


def approved_model(user_id: UUID, step: str) -> str | None:
    """The model the owner approved for this model step, if any."""
    with connect() as conn:
        row: Any = conn.execute(
            "SELECT model FROM step_models WHERE user_id = %s AND step = %s",
            (settings_owner(user_id), step),
        ).fetchone()
    return row["model"] if row else None


def _ordered(user_id: UUID, step: str, models: Sequence[str]) -> Sequence[str]:
    """The Fallback List for this call: a Challenger alone, or the approved model first."""
    challenger = _challenger.get()
    if challenger and challenger.step == step:
        return (challenger.model,)
    approved = approved_model(user_id, step)
    return (approved, *(m for m in models if m != approved)) if approved else models


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


def likely_model(
    user_id: UUID, step: str, models: Sequence[str], data_class: DataClass
) -> str | None:
    """The model a call would use now, by complete_first's own rules, for a cost estimate: the
    first one that can take it, skipping a paid model once this month's cap is reached."""
    settings = model_settings(user_id)
    with connect() as conn:
        cap, spent = cap_and_spent(conn, settings_owner(user_id))
    for model in _ordered(user_id, STEP_OF.get(step, step), models):
        if _skip(model, data_class, settings) or (_is_paid(model) and spent >= cap):
            continue
        return model
    return None


def model_status(user_id: UUID) -> ModelStatus:
    """Which models personal-data work uses now, by the same rules complete_first follows."""
    settings = model_settings(user_id)
    with connect() as conn:
        cap, spent = cap_and_spent(conn, settings_owner(user_id))
    if not has_keys(HAIKU):
        note: str | None = NO_KEY
    elif _skip(HAIKU, DataClass.PERSONAL, settings):
        note = settings["paid_unavailable_reason"]
    elif spent >= cap:
        note = AT_CAP
    else:
        note = None
    free_ready = any(
        not _skip(model, DataClass.PERSONAL, settings)
        for model in PERSONAL_MODELS
        if not _is_paid(model)
    )
    return ModelStatus(
        paid=note is None,
        note=note,
        groq_zdr_confirmed=settings["groq_zdr_confirmed"],
        personal_work_waits=note is not None and not free_ready,
    )


def _failed(user_id: UUID, step: str) -> None:
    """Count a whole Fallback List failing, and pause the step at the third in a row."""
    with connect() as conn:
        conn.execute(
            f"""INSERT INTO step_pauses AS s (user_id, step, failures)
                VALUES (%(user)s, %(step)s, 1)
                ON CONFLICT (user_id, step) DO UPDATE SET
                    failures = CASE WHEN s.failures + 1 >= {PAUSE_AFTER_FAILURES} THEN 0
                                    ELSE s.failures + 1 END,
                    paused_until = CASE WHEN s.failures + 1 >= {PAUSE_AFTER_FAILURES}
                                        THEN now() + interval '{PAUSE_MINUTES} minutes'
                                        ELSE s.paused_until END""",
            {"user": user_id, "step": step},
        )


def paused_steps(user_id: UUID) -> list[tuple[str, datetime]]:
    """Each model step paused now, and until when."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT step, paused_until FROM step_pauses
               WHERE user_id = %s AND paused_until > now() ORDER BY step""",
            (user_id,),
        ).fetchall()
    return [(row["step"], row["paused_until"]) for row in rows]


def resume_steps(user_id: UUID, steps: Sequence[str]) -> None:
    """Start these model steps again now, as Retry does, with their failure count cleared."""
    with connect() as conn:
        conn.execute(
            "DELETE FROM step_pauses WHERE user_id = %s AND step = ANY(%s)", (user_id, list(steps))
        )


def can_take_personal(user_id: UUID, model: str) -> bool:
    """Whether this model may receive personal-data work for the person now."""
    return not _skip(model, DataClass.PERSONAL, model_settings(user_id))


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
    model_step = STEP_OF.get(step, step)
    until = dict(paused_steps(user_id)).get(model_step)
    if until:
        raise StepPaused(
            f"{STEP_LABELS.get(model_step, model_step)} is paused until {until:%H:%M} UTC"
        )
    models = _ordered(user_id, model_step, models)
    for model in models:
        rule = MODELS.get(model)
        if rule is None or data_class not in rule.data_classes:
            raise NotEligible(f"{model} may not receive {data_class.value} data")
    settings = model_settings(user_id)
    failures: list[str] = []
    rate_limited = False
    # Only models that were called and failed count towards a pause, not the cap or missing keys.
    called_and_failed = False
    for model in models:
        if _skip(model, data_class, settings):
            continue
        for attempt in range(1, RATE_LIMIT_TRIES + 1):
            try:
                completion = complete(
                    user_id=user_id,
                    model=model,
                    data_class=data_class,
                    step=step,
                    messages=messages,
                    max_output_tokens=max_output_tokens,
                    application_id=application_id,
                )
                used = _used.get()
                if used is not None:
                    used[model_step] = completion.model
                resume_steps(user_id, [model_step])
                return completion
            except CapReached:
                if user_id == EVAL_USER_ID:
                    raise
                failures.append(f"{model}: monthly cap reached")
            except ModelUnavailable as error:
                if error.rate_limited and attempt < RATE_LIMIT_TRIES:
                    # ponytail: waits in the worker, holding the queue; fine for one person.
                    time.sleep(RATE_LIMIT_WAIT_SECONDS)
                    continue
                if error.out_of_credit and _is_paid(model):
                    _paid_out_until_tomorrow(user_id)
                rate_limited = rate_limited or error.rate_limited
                called_and_failed = True
                failures.append(str(error))
            break
    if called_and_failed:
        _failed(user_id, model_step)
    # Every failure's type is kept, so a rate limit still reads as one: evals count it as not run.
    raise ModelUnavailable(
        "; ".join(failures) or "No model is set up for this step", rate_limited=rate_limited
    )
