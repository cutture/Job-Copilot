import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest

from job_copilot import gateway
from job_copilot.gateway import CapReached, DataClass, ModelUnavailable, NotEligible
from tests.conftest import TEST_DB, FakeProvider, real_call_provider

USER = UUID("00000000-0000-0000-0000-000000000001")
GROQ_POSTING_MODEL = "groq/openai/gpt-oss-20b"
HAIKU = "anthropic/claude-haiku-5-5"
RESUME_TEXT = "Sam Rivera, 12 Example Street, sam@example.com"


def ask(model: str, data_class: DataClass, text: str = "hello") -> gateway.Completion:
    return gateway.complete(
        user_id=USER,
        model=model,
        data_class=data_class,
        step="test",
        messages=[{"role": "user", "content": text}],
        max_output_tokens=100,
    )


def spend(amount: str, when: str = "now()") -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            f"""INSERT INTO model_calls
                (user_id, model, step, input_tokens, output_tokens, cost_usd, created_at)
                VALUES (%s, 'seed', 'seed', 0, 0, %s, {when})""",
            (USER, Decimal(amount)),
        )


def calls() -> list[tuple[Any, ...]]:
    with psycopg.connect(TEST_DB) as conn:
        return conn.execute(
            "SELECT model, input_tokens, output_tokens, cost_usd, trace_id FROM model_calls"
        ).fetchall()


def test_personal_data_never_reaches_an_ineligible_model(provider: FakeProvider) -> None:
    with pytest.raises(NotEligible):
        ask(GROQ_POSTING_MODEL, DataClass.PERSONAL, RESUME_TEXT)

    assert provider.received == []
    assert calls() == []


def test_an_undeclared_model_is_refused(provider: FakeProvider) -> None:
    with pytest.raises(NotEligible):
        ask("openrouter/some/model:free", DataClass.POSTING)

    assert provider.received == []


def test_personal_data_can_reach_an_eligible_model(provider: FakeProvider) -> None:
    assert ask(HAIKU, DataClass.PERSONAL, RESUME_TEXT).text == provider.text
    assert provider.received[0]["model"] == HAIKU


def test_each_call_records_model_tokens_and_cost(provider: FakeProvider) -> None:
    provider.input_tokens, provider.output_tokens = 1_000_000, 1_000_000

    ask(HAIKU, DataClass.PERSONAL)

    # Worked example from the published rate of $0.10 input and $0.50 output per million.
    assert calls() == [(HAIKU, 1_000_000, 1_000_000, Decimal("0.600000"), None)]


def test_free_model_calls_are_recorded_at_no_cost(provider: FakeProvider) -> None:
    ask(GROQ_POSTING_MODEL, DataClass.POSTING)

    assert calls()[0][3] == Decimal("0")


def test_a_paid_call_stops_at_the_cap(provider: FakeProvider) -> None:
    spend("10.00")

    with pytest.raises(CapReached):
        ask(HAIKU, DataClass.PERSONAL)

    assert provider.received == []


def test_a_paid_call_stops_when_it_could_pass_the_cap(provider: FakeProvider) -> None:
    spend("9.9999999")

    with pytest.raises(CapReached):
        ask(HAIKU, DataClass.PERSONAL)

    assert provider.received == []


def test_free_models_keep_working_at_the_cap(provider: FakeProvider) -> None:
    spend("10.00")

    ask(GROQ_POSTING_MODEL, DataClass.POSTING)

    assert len(provider.received) == 1


def test_last_months_spending_does_not_count(provider: FakeProvider) -> None:
    spend("10.00", "now() - interval '40 days'")

    ask(HAIKU, DataClass.PERSONAL)

    assert len(provider.received) == 1


def test_the_cap_is_configurable_per_user(provider: FakeProvider) -> None:
    spend("10.00")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE users SET monthly_cap_usd = 20 WHERE id = %s", (USER,))
    try:
        ask(HAIKU, DataClass.PERSONAL)
    finally:
        with psycopg.connect(TEST_DB, autocommit=True) as conn:
            conn.execute("UPDATE users SET monthly_cap_usd = 10 WHERE id = %s", (USER,))

    assert len(provider.received) == 1


def test_provider_errors_and_logs_never_contain_the_text(
    provider: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    provider.error = RuntimeError(f"bad request: {RESUME_TEXT}")

    with caplog.at_level(logging.DEBUG), pytest.raises(ModelUnavailable) as raised:
        ask(HAIKU, DataClass.PERSONAL, RESUME_TEXT)

    assert RESUME_TEXT not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    assert RESUME_TEXT not in caplog.text


def test_successful_calls_log_ids_only(
    provider: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    provider.text = "model output that must stay private"

    with caplog.at_level(logging.DEBUG):
        ask(HAIKU, DataClass.PERSONAL, RESUME_TEXT)

    assert RESUME_TEXT not in caplog.text
    assert provider.text not in caplog.text


def test_tracing_is_off_without_settings(
    provider: FakeProvider, traces: list[dict[str, Any]]
) -> None:
    ask(HAIKU, DataClass.PERSONAL, RESUME_TEXT)

    assert traces == []
    assert calls()[0][4] is None


def test_traces_contain_no_text_and_their_id_is_stored(
    provider: FakeProvider, traces: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://eu.langfuse.example.com")
    provider.text = "model output that must stay private"

    ask(HAIKU, DataClass.PERSONAL, RESUME_TEXT)

    sent = json.dumps(traces)
    assert len(traces) == 1
    assert "Sam Rivera" not in sent
    assert provider.text not in sent
    assert calls()[0][4] == traces[0]["trace_id"]
    assert traces[0]["host"] == "https://eu.langfuse.example.com"


def test_tracing_needs_a_region_chosen_at_setup(
    provider: FakeProvider, traces: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    ask(HAIKU, DataClass.PERSONAL)

    assert traces == []


def test_a_tracing_failure_does_not_lose_the_answer(
    provider: FakeProvider, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://eu.langfuse.example.com")

    def broken(*_: Any) -> None:
        raise RuntimeError("langfuse down")

    monkeypatch.setattr(gateway, "send_trace", broken)

    assert ask(HAIKU, DataClass.PERSONAL).text == provider.text
    assert calls()[0][4] is None


def test_the_provider_adapter_reads_litellm_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    real = litellm.completion
    monkeypatch.setattr(
        litellm, "completion", lambda **kw: real(**kw, mock_response="Adapter answer")
    )

    answer = real_call_provider(GROQ_POSTING_MODEL, [{"role": "user", "content": "hi"}], 10)

    assert answer.text == "Adapter answer"
    assert answer.input_tokens > 0
