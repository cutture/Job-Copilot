"""Challenger runs, recommendations and the owner's approval of a step's model."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import eval_runs, evals, gateway, worker
from job_copilot.db import SEEDED_USER_ID
from job_copilot.gateway import DataClass
from tests.conftest import TEST_DB, FakeProvider
from tests.test_evals import LOADED, OWNER, cases_file

HAIKU = gateway.HAIKU
GROQ = gateway.GROQ_PERSONAL
SONNET = gateway.SONNET
RATING_GROQ = gateway.Challenger("rating", GROQ)


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


def test_an_approved_pack_writing_model_writes_the_cover_letter_too_but_not_verification(
    client: TestClient, provider: FakeProvider
) -> None:
    confirm_groq_zdr(client)
    use_for("pack", GROQ)

    assert ask("pack_cover_letter") == GROQ
    assert ask("pack_verification") == HAIKU


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

    with gateway.challenging(gateway.Challenger("rating", GROQ)):
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


def test_a_sonnet_challenger_rates_with_personal_data_at_its_price(
    provider: FakeProvider,
) -> None:
    with gateway.challenging(gateway.Challenger("rating", SONNET)):
        assert ask("rating") == SONNET

    with psycopg.connect(TEST_DB) as conn:
        cost = conn.execute("SELECT cost_usd FROM model_calls").fetchone()
    # 10 tokens in at $2 a million, 5 out at $10 a million.
    assert cost == (Decimal("0.00007"),)


def models_used(**overrides: Any) -> dict[str, str]:
    return {"rating": HAIKU, "pack": HAIKU, "verification": HAIKU, **overrides}


def runs() -> list[tuple[Any, ...]]:
    with psycopg.connect(TEST_DB) as conn:
        return conn.execute(
            """SELECT r.challenger_step, r.challenger_model,
                      (SELECT count(*) FROM jobs j WHERE (j.payload ->> 'run_id')::bigint = r.id)
               FROM eval_runs r ORDER BY r.id"""
        ).fetchall()


def test_groq_challenges_rating_and_pack_writing_once_a_week(
    client: TestClient, provider: FakeProvider
) -> None:
    confirm_groq_zdr(client)
    now = datetime.now(UTC).replace(hour=23)

    worker.schedule_daily_evals(now)
    worker.schedule_daily_evals(now)

    rating_cases = sum("passes" not in c["expect"] for c in LOADED["cases"])
    pack_cases = sum(bool(eval_runs.PACK_LABELS & c["expect"].keys()) for c in LOADED["cases"])
    assert runs() == [(None, None, 24), ("rating", GROQ, rating_cases), ("pack", GROQ, pack_cases)]

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE eval_runs SET started_at = started_at - interval '8 days'")
    worker.schedule_daily_evals(now)
    assert [r[0] for r in runs()][3:] == [None, "rating", "pack"]


def test_no_challenger_runs_for_a_model_already_approved_or_one_that_cant_take_the_data(
    client: TestClient, provider: FakeProvider
) -> None:
    worker.schedule_daily_evals(datetime.now(UTC).replace(hour=23))
    # Groq's Zero Data Retention isn't confirmed, so it can't run these steps.
    assert [r[0] for r in runs()] == [None]

    confirm_groq_zdr(client)
    use_for("rating", GROQ)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM eval_runs")
    worker.schedule_daily_evals(datetime.now(UTC).replace(hour=23))
    assert [r[0] for r in runs()] == [None, "pack"]


def test_a_challenger_run_uses_its_model_for_its_step_and_records_the_models(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    confirm_groq_zdr(client)

    run_id = evals.run(
        OWNER,
        cases_file(tmp_path, "scoring-thin-posting", "filter-on-site-elsewhere"),
        RATING_GROQ,
    )

    run = client.get(f"/api/eval-runs/{run_id}").json()
    assert (run["challenger_label"], run["challenger_name"]) == (
        "Rating Matches",
        "Groq gpt-oss-120b (free)",
    )
    # Only the cases that use the step run.
    [result] = run["results"]
    assert result["models"] == {"Rating Matches": "Groq gpt-oss-120b (free)"}


def test_a_rating_challenger_stops_after_rating_even_on_a_pack_case(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    confirm_groq_zdr(client)

    run_id = evals.run(OWNER, cases_file(tmp_path, "pack-keeps-reworded-claims"), RATING_GROQ)

    [result] = client.get(f"/api/eval-runs/{run_id}").json()["results"]
    assert list(result["models"]) == ["Rating Matches"]
    assert {r["model"] for r in provider.received} == {GROQ}


def test_a_failing_challenger_run_never_turns_on_the_banner(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    confirm_groq_zdr(client)
    provider.errors = {GROQ: ValueError("unusable")}
    provider.answers = {GROQ: "not json"}

    evals.run(OWNER, cases_file(tmp_path, "scoring-strong-match"), RATING_GROQ)

    assert client.get("/api/evals/status").json()["failing"] is False
    # Nor does it count as today's daily run.
    worker.schedule_daily_evals(datetime.now(UTC).replace(hour=23))
    assert None in [r[0] for r in runs()]
