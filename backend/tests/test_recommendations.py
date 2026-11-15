"""Recommending a Challenger, and the owner approving, dismissing or switching back."""

import json
from decimal import Decimal
from typing import Any

import psycopg
from fastapi.testclient import TestClient

from job_copilot import gateway
from job_copilot.db import EVAL_USER_ID, SEEDED_USER_ID
from job_copilot.tracked_scores import CaseScores
from tests.conftest import TEST_DB, FakeProvider

HAIKU, GROQ, SONNET = gateway.HAIKU, gateway.GROQ_PERSONAL, gateway.SONNET


def past_run(
    weeks_ago: int,
    model: str,
    challenger: bool,
    band_right: int,
    hard: bool = False,
    step: str = "rating",
) -> None:
    """A finished run of 4 rating cases, `band_right` of them with the right Band."""
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        run: Any = conn.execute(
            """INSERT INTO eval_runs (user_id, deepeval_version, started_at, finished_at,
                                      challenger_step, challenger_model)
               VALUES (%s, 'x', now() - %s * interval '1 week', now() - %s * interval '1 week',
                       %s, %s) RETURNING id""",
            (
                SEEDED_USER_ID,
                weeks_ago,
                weeks_ago,
                step if challenger else None,
                model if challenger else None,
            ),
        ).fetchone()
        for i in range(4):
            scores = CaseScores(band_exact=i < band_right)
            conn.execute(
                """INSERT INTO eval_results (user_id, run_id, case_id, area, status,
                                            hard_failure, labels_checked, reason, scores, models)
                   VALUES (%s, %s, %s, 'scoring', %s, %s, true, 'r', %s, %s)""",
                (
                    SEEDED_USER_ID,
                    run[0],
                    f"case-{i}",
                    "failed" if hard and i == 0 else "passed",
                    hard and i == 0,
                    scores.model_dump_json(),
                    json.dumps({step: model}),
                ),
            )


def three_weeks(challenger_right: int, current_right: int, **challenger: Any) -> None:
    for week in (3, 2, 1):
        past_run(week, HAIKU, challenger=False, band_right=current_right)
        past_run(week, GROQ, challenger=True, band_right=challenger_right, **challenger)


def recommended(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/recommendations")
    assert response.status_code == 200
    recommendations: list[dict[str, Any]] = response.json()
    return recommendations


def test_a_challenger_better_on_its_steps_scores_for_three_weeks_is_recommended(
    client: TestClient, provider: FakeProvider
) -> None:
    three_weeks(challenger_right=4, current_right=3)

    [recommendation] = recommended(client)
    assert (recommendation["step"], recommendation["model"]) == ("rating", GROQ)
    assert recommendation["model_name"] == "Groq gpt-oss-120b (free)"
    assert recommendation["current_name"] == "Claude Haiku 5.5"
    [band] = [e for e in recommendation["evidence"] if e["score"] == "Exact Band"]
    assert (band["challenger"], band["current"]) == (100, 75)


def test_two_weeks_arent_enough(client: TestClient, provider: FakeProvider) -> None:
    for week in (2, 1):
        past_run(week, HAIKU, challenger=False, band_right=3)
        past_run(week, GROQ, challenger=True, band_right=4)

    assert recommended(client) == []


def test_any_hard_failure_rules_a_challenger_out(
    client: TestClient, provider: FakeProvider
) -> None:
    three_weeks(challenger_right=4, current_right=3, hard=True)

    assert recommended(client) == []


def test_no_better_is_not_enough(client: TestClient, provider: FakeProvider) -> None:
    three_weeks(challenger_right=3, current_right=3)

    assert recommended(client) == []


def test_a_challenger_whose_price_would_pass_the_cap_isnt_recommended(
    client: TestClient, provider: FakeProvider
) -> None:
    for week in (3, 2, 1):
        past_run(week, HAIKU, challenger=False, band_right=3)
        past_run(week, SONNET, challenger=True, band_right=4)
    # Last month's rating: 3M tokens in, 0.5M out, about $0.55 on Haiku; on Sonnet, $11.
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO model_calls (user_id, model, step, input_tokens, output_tokens, cost_usd)
               VALUES (%s, %s, 'rating', 3000000, 500000, 0.55)""",
            (SEEDED_USER_ID, HAIKU),
        )

    assert recommended(client) == []


def test_approving_switches_the_step_and_starts_an_eval_run_on_it(
    client: TestClient, provider: FakeProvider
) -> None:
    three_weeks(challenger_right=4, current_right=3)

    response = client.post("/api/recommendations/approve", json={"step": "rating", "model": GROQ})

    assert response.status_code == 200
    assert gateway.approved_model(SEEDED_USER_ID, "rating") == GROQ
    assert gateway.approved_model(EVAL_USER_ID, "rating") == GROQ
    with psycopg.connect(TEST_DB) as conn:
        queued = conn.execute(
            """SELECT count(*) FROM eval_runs r WHERE r.challenger_model IS NULL
               AND EXISTS (SELECT 1 FROM jobs j WHERE (j.payload ->> 'run_id')::bigint = r.id)"""
        ).fetchone()
    assert queued == (1,)
    assert recommended(client) == []


def test_only_a_current_recommendation_can_be_approved(
    client: TestClient, provider: FakeProvider
) -> None:
    response = client.post("/api/recommendations/approve", json={"step": "rating", "model": SONNET})

    assert response.status_code == 409
    assert gateway.approved_model(SEEDED_USER_ID, "rating") is None


def test_a_dismissed_recommendation_stays_away_until_a_newer_challenger_run(
    client: TestClient, provider: FakeProvider
) -> None:
    three_weeks(challenger_right=4, current_right=3)

    client.post("/api/recommendations/dismiss", json={"step": "rating", "model": GROQ})
    assert recommended(client) == []

    past_run(0, HAIKU, challenger=False, band_right=3)
    past_run(0, GROQ, challenger=True, band_right=4)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            "UPDATE eval_runs SET finished_at = now() + interval '1 minute' WHERE "
            "id = (SELECT max(id) FROM eval_runs)"
        )
    assert len(recommended(client)) == 1


def test_settings_show_each_steps_model_and_switch_back(
    client: TestClient, provider: FakeProvider
) -> None:
    three_weeks(challenger_right=4, current_right=3)
    client.post("/api/recommendations/approve", json={"step": "rating", "model": GROQ})

    steps = {s["step"]: s for s in client.get("/api/step-models").json()}
    assert (steps["rating"]["model_name"], steps["rating"]["approved"]) == (
        "Groq gpt-oss-120b (free)",
        True,
    )
    assert steps["pack"]["approved"] is False

    assert client.delete("/api/step-models/rating").status_code == 200
    assert gateway.approved_model(SEEDED_USER_ID, "rating") is None


def test_the_monthly_cost_on_the_challenger_is_shown(
    client: TestClient, provider: FakeProvider
) -> None:
    three_weeks(challenger_right=4, current_right=3)

    [recommendation] = recommended(client)
    assert Decimal(recommendation["monthly_cost_usd"]) == 0
