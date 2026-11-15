"""Free models that don't train on the person's data, when there's no paid key or credit."""

import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import gateway, worker
from job_copilot.db import EVAL_USER_ID, SEEDED_USER_ID
from job_copilot.filter import FILTER_MODEL
from job_copilot.gateway import CapReached, DataClass, ModelUnavailable, NotEligible
from tests.conftest import TEST_DB, FakeProvider
from tests.test_filter import facts
from tests.test_rating import POSTING, answer

HAIKU = "anthropic/claude-haiku-5-5"
GROQ_PERSONAL = "groq/openai/gpt-oss-120b"
CLOUDFLARE_PERSONAL = "cloudflare/@cf/openai/gpt-oss-120b"
GROQ_POSTING = "groq/openai/gpt-oss-20b"


class CreditBalanceTooLow(Exception):
    """Stands in for the provider's error when the account has no credit left."""

    def __str__(self) -> str:
        return "Your credit balance is too low to access the Anthropic API."


class AuthenticationError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


def ask(user_id: Any = SEEDED_USER_ID, data_class: DataClass = DataClass.PERSONAL) -> str:
    models = gateway.PERSONAL_MODELS if data_class is DataClass.PERSONAL else gateway.POSTING_MODELS
    return gateway.complete_first(
        user_id=user_id,
        models=models,
        data_class=data_class,
        step="test",
        messages=[{"role": "user", "content": "hello"}],
        max_output_tokens=100,
    ).model


def confirm_groq_zdr(client: TestClient) -> None:
    assert client.put("/api/model-settings/groq-zdr", json={"confirmed": True}).status_code == 200


def models_asked(provider: FakeProvider) -> list[str]:
    return [r["model"] for r in provider.received]


def spend(user_id: Any, amount: str) -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO model_calls (user_id, model, step, input_tokens, output_tokens, cost_usd)
               VALUES (%s, 'seed', 'seed', 0, 0, %s)""",
            (user_id, Decimal(amount)),
        )


def test_with_a_paid_key_haiku_writes_first(provider: FakeProvider) -> None:
    assert ask() == HAIKU


def test_without_an_anthropic_key_no_paid_call_is_tried(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    confirm_groq_zdr(client)

    assert ask() == GROQ_PERSONAL
    assert models_asked(provider) == [GROQ_PERSONAL]


def test_groq_gets_no_personal_data_until_zero_data_retention_is_confirmed(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")

    with pytest.raises(ModelUnavailable):
        ask()
    assert provider.received == []
    # Posting text needs no such confirmation.
    assert ask(data_class=DataClass.POSTING) == GROQ_POSTING


def test_cloudflare_is_used_when_groq_isnt_confirmed_and_its_keys_are_set(
    provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "test-token")

    assert ask() == CLOUDFLARE_PERSONAL


def test_a_haiku_outage_falls_to_the_next_eligible_model(
    client: TestClient, provider: FakeProvider
) -> None:
    confirm_groq_zdr(client)
    provider.errors = {HAIKU: TimeoutError()}

    assert ask() == GROQ_PERSONAL
    # An outage isn't a missing credit: the next call tries Haiku again.
    provider.errors = {}
    assert ask() == HAIKU


@pytest.mark.parametrize(
    "error", [CreditBalanceTooLow(), AuthenticationError(), PermissionDeniedError()]
)
def test_no_credit_or_a_bad_key_moves_the_day_to_free_models_and_settings_says_why(
    client: TestClient, provider: FakeProvider, error: Exception
) -> None:
    confirm_groq_zdr(client)
    provider.errors = {HAIKU: error}

    assert ask() == GROQ_PERSONAL
    provider.errors = {}
    assert ask() == GROQ_PERSONAL
    assert models_asked(provider) == [HAIKU, GROQ_PERSONAL, GROQ_PERSONAL]

    settings = client.get("/api/model-settings").json()
    assert settings["mode"] == "free"
    assert "until tomorrow" in settings["note"]
    assert "Anthropic Console" in settings["note"]


def test_haiku_is_tried_again_the_next_day(client: TestClient, provider: FakeProvider) -> None:
    confirm_groq_zdr(client)
    provider.errors = {HAIKU: CreditBalanceTooLow()}
    ask()
    provider.errors = {}
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            "UPDATE users SET paid_unavailable_until = %s WHERE id = %s",
            (datetime.now(UTC) - timedelta(seconds=1), SEEDED_USER_ID),
        )

    assert ask() == HAIKU
    assert client.get("/api/model-settings").json()["mode"] == "paid"


def test_at_the_monthly_cap_free_models_are_used(
    client: TestClient, provider: FakeProvider
) -> None:
    confirm_groq_zdr(client)
    spend(SEEDED_USER_ID, "10.00")

    assert ask() == GROQ_PERSONAL
    assert models_asked(provider) == [GROQ_PERSONAL]
    settings = client.get("/api/model-settings").json()
    assert settings["mode"] == "free"
    assert "until the 1st" in settings["note"]


def test_evals_stop_at_their_own_cap_instead_of_testing_another_model(
    client: TestClient, provider: FakeProvider
) -> None:
    confirm_groq_zdr(client)
    spend(EVAL_USER_ID, "3.00")

    with pytest.raises(CapReached):
        ask(EVAL_USER_ID)
    assert provider.received == []


def test_a_list_naming_a_posting_only_model_for_personal_data_is_refused(
    provider: FakeProvider,
) -> None:
    with pytest.raises(NotEligible):
        gateway.complete_first(
            user_id=SEEDED_USER_ID,
            models=(GROQ_POSTING,),
            data_class=DataClass.PERSONAL,
            step="test",
            messages=[{"role": "user", "content": "hello"}],
            max_output_tokens=100,
        )
    assert provider.received == []


def test_every_model_that_may_train_on_data_is_kept_from_personal_data() -> None:
    # Adding any model for personal data, such as a Groq preview model, fails here first, so
    # its terms get checked.
    personal = {m for m, rule in gateway.MODELS.items() if DataClass.PERSONAL in rule.data_classes}

    # Sonnet is under the same Anthropic terms as Haiku; it runs only as a Challenger.
    assert personal == {HAIKU, GROQ_PERSONAL, CLOUDFLARE_PERSONAL, gateway.SONNET}
    assert set(gateway.PERSONAL_MODELS) == personal - {gateway.SONNET}


def test_a_match_is_rated_by_the_free_model_without_a_paid_key(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    confirm_groq_zdr(client)
    provider.answers = {FILTER_MODEL: facts(), GROQ_PERSONAL: json.dumps(answer())}

    created = client.post("/api/job-postings", json={"text": POSTING}).json()
    while worker.run_once():
        pass

    posting = next(p for p in client.get("/api/job-postings").json() if p["id"] == created["id"])
    assert posting["match"]["band"] is not None
    assert HAIKU not in models_asked(provider)


def test_settings_show_free_mode_without_a_key_and_the_zdr_checkbox(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")

    settings = client.get("/api/model-settings").json()
    assert (settings["mode"], settings["groq_zdr_confirmed"]) == ("free", False)
    assert settings["note"].startswith("No Anthropic key is set")
    assert ".env" in settings["note"]
    assert settings["personal_work_waits"] is True

    confirm_groq_zdr(client)
    assert client.get("/api/model-settings").json()["personal_work_waits"] is False


class RateLimitError(Exception):
    """Stands in for a provider's per-minute limit."""


def test_a_rate_limited_free_model_is_waited_for_and_asked_again(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    # Cloudflare is set up too, so only waiting for Groq can explain Groq's answer.
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "test-token")
    confirm_groq_zdr(client)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    limited = iter([RateLimitError(), RateLimitError()])

    def limited_then_answer(model: str, messages: Any, max_tokens: int) -> gateway.ProviderAnswer:
        provider.received.append({"model": model})
        error = next(limited, None)
        if error:
            raise error
        return gateway.ProviderAnswer("answer", 10, 5)

    monkeypatch.setattr(gateway, "call_provider", limited_then_answer)

    assert ask() == GROQ_PERSONAL


def test_a_model_still_rate_limited_after_waiting_falls_to_the_next(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "test-token")
    confirm_groq_zdr(client)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    provider.errors = {GROQ_PERSONAL: RateLimitError()}

    assert ask() == CLOUDFLARE_PERSONAL


@pytest.mark.parametrize(
    ("model", "name"),
    [
        (HAIKU, "Claude Haiku 5.5"),
        (GROQ_PERSONAL, "Groq gpt-oss-120b (free)"),
        (CLOUDFLARE_PERSONAL, "Cloudflare gpt-oss-120b (free)"),
        ("an/unknown-model", "an/unknown-model"),
    ],
)
def test_packs_name_the_model_that_wrote_them_readably(model: str, name: str) -> None:
    assert gateway.model_name(model) == name
