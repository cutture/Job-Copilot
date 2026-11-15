"""Challenger runs, recommendations and the owner's approval of a step's model."""

from decimal import Decimal
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import gateway
from job_copilot.db import SEEDED_USER_ID
from job_copilot.gateway import DataClass
from tests.conftest import TEST_DB, FakeProvider

HAIKU = gateway.HAIKU
GROQ = gateway.GROQ_PERSONAL
SONNET = gateway.SONNET


def ask(step: str = "rating") -> str:
    return gateway.complete_first(
        user_id=SEEDED_USER_ID,
        models=gateway.PERSONAL_MODELS,
        data_class=DataClass.PERSONAL,
        step=step,
        messages=[{"role": "user", "content": "hello"}],
        max_output_tokens=100,
    ).model


def use_for(step: str, model: str) -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO step_models (user_id, step, model) VALUES (%s, %s, %s)",
            (SEEDED_USER_ID, step, model),
        )


def confirm_groq_zdr(client: TestClient) -> None:
    client.put("/api/model-settings/groq-zdr", json={"confirmed": True})


def test_each_step_belongs_to_one_model_step() -> None:
    assert gateway.STEP_OF == {
        "filter": "filter",
        "resume_evidence": "evidence",
        "rating": "rating",
        "pack_resume": "pack",
        "pack_cover_letter": "pack",
        "pack_verification": "verification",
    }


def test_an_approved_model_goes_first_for_its_step_only(
    client: TestClient, provider: FakeProvider
) -> None:
    confirm_groq_zdr(client)
    use_for("rating", GROQ)

    assert ask("rating") == GROQ
    assert ask("pack_resume") == HAIKU


def test_an_approved_model_still_falls_back_when_it_fails(
    client: TestClient, provider: FakeProvider
) -> None:
    confirm_groq_zdr(client)
    use_for("rating", GROQ)
    provider.errors = {GROQ: TimeoutError()}

    assert ask("rating") == HAIKU


def test_a_challenger_run_pins_its_step_to_the_challenger_alone(
    client: TestClient, provider: FakeProvider
) -> None:
    confirm_groq_zdr(client)
    provider.errors = {GROQ: TimeoutError()}

    with gateway.challenging("rating", GROQ):
        # No fallback: a Challenger's failure is its own result.
        with pytest.raises(gateway.ModelUnavailable):
            ask("rating")
        assert ask("pack_resume") == HAIKU


def test_calls_record_the_model_each_step_used(client: TestClient, provider: FakeProvider) -> None:
    confirm_groq_zdr(client)
    use_for("pack", GROQ)

    with gateway.recording_models() as used:
        ask("rating")
        ask("pack_resume")
        ask("pack_verification")

    assert used == {"rating": HAIKU, "pack": GROQ, "verification": HAIKU}


def test_sonnet_may_receive_personal_data_and_is_priced(provider: FakeProvider) -> None:
    rule = gateway.MODELS[SONNET]

    assert DataClass.PERSONAL in rule.data_classes
    assert (rule.input_usd_per_million, rule.output_usd_per_million) == (
        Decimal("2.00"),
        Decimal("10.00"),
    )
    assert gateway.model_name(SONNET) == "Claude Sonnet 5.5"


def models_used(**overrides: Any) -> dict[str, str]:
    return {"rating": HAIKU, "pack": HAIKU, "verification": HAIKU, **overrides}
