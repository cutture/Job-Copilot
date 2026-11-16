"""A step that keeps failing pauses alone, waits without spending, and starts again."""

import json
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import gateway, rating, worker
from job_copilot.db import SEEDED_USER_ID
from job_copilot.filter import FILTER_MODEL
from job_copilot.gateway import DataClass
from tests.conftest import TEST_DB, FakeProvider
from tests.test_filter import facts
from tests.test_rating import POSTING, answer


def ask(step: str = "rating") -> str:
    return gateway.complete_first(
        user_id=SEEDED_USER_ID,
        models=gateway.PERSONAL_MODELS,
        data_class=DataClass.PERSONAL,
        step=step,
        messages=[{"role": "user", "content": "hello"}],
        max_output_tokens=100,
    ).model


def fail_times(n: int, step: str = "rating") -> None:
    for _ in range(n):
        with pytest.raises(gateway.ModelUnavailable):
            ask(step)


def age_pause(minutes: int) -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            "UPDATE step_pauses SET paused_until = paused_until - %s * interval '1 minute'",
            (minutes,),
        )


def test_three_failures_of_the_whole_list_in_a_row_pause_only_that_step(
    provider: FakeProvider,
) -> None:
    provider.error = TimeoutError()
    fail_times(3)
    asked = len(provider.received)

    with pytest.raises(gateway.StepPaused):
        ask("rating")
    # Paused: no model is called, so nothing is spent on a call that would fail.
    assert len(provider.received) == asked

    provider.error = None
    assert ask("pack_resume") == gateway.HAIKU


def test_a_success_clears_the_count(provider: FakeProvider) -> None:
    provider.error = TimeoutError()
    fail_times(2)
    provider.error = None
    ask()
    provider.error = TimeoutError()
    fail_times(2)

    provider.error = None
    assert ask() == gateway.HAIKU


def test_reaching_the_cap_isnt_a_failure(provider: FakeProvider, monkeypatch: Any) -> None:
    monkeypatch.delenv("GROQ_API_KEY")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO model_calls (user_id, model, step, input_tokens, output_tokens,
                                        cost_usd) VALUES (%s, 'seed', 'seed', 0, 0, 10)""",
            (SEEDED_USER_ID,),
        )
    for _ in range(4):
        with pytest.raises(gateway.ModelUnavailable) as raised:
            ask()
        assert not isinstance(raised.value, gateway.StepPaused)


def test_a_paused_step_tries_again_after_30_minutes(provider: FakeProvider) -> None:
    provider.error = TimeoutError()
    fail_times(3)
    provider.error = None
    age_pause(31)

    assert ask() == gateway.HAIKU


def test_a_paused_steps_queued_work_waits_while_other_work_goes_on(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.error = TimeoutError()
    fail_times(3)
    provider.error = None
    provider.answers = {FILTER_MODEL: facts(), rating.RATING_MODEL: json.dumps(answer())}

    created = client.post("/api/job-postings", json={"text": POSTING}).json()
    while worker.run_once():
        pass

    # Filter ran; rating waits in the queue, untouched.
    [posting] = [p for p in client.get("/api/job-postings").json() if p["id"] == created["id"]]
    assert (posting["status"], posting["rating_state"]) == ("received", "rating")

    age_pause(31)
    while worker.run_once():
        pass
    [posting] = [p for p in client.get("/api/job-postings").json() if p["id"] == created["id"]]
    assert posting["match"] is not None


def test_retrying_a_match_that_wasnt_rated_resumes_rating_at_once(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.answers = {FILTER_MODEL: facts()}
    provider.errors = {gateway.HAIKU: TimeoutError()}
    created = client.post("/api/job-postings", json={"text": POSTING}).json()
    while worker.run_once():
        pass
    fail_times(2)
    [posting] = [p for p in client.get("/api/job-postings").json() if p["id"] == created["id"]]
    assert posting["status"] == "not_rated"

    provider.errors = {}
    provider.answers = {FILTER_MODEL: facts(), rating.RATING_MODEL: json.dumps(answer())}
    response = client.post(f"/api/job-postings/{created['id']}/retry-rating")
    assert response.status_code == 202
    while worker.run_once():
        pass

    [posting] = [p for p in client.get("/api/job-postings").json() if p["id"] == created["id"]]
    assert posting["match"] is not None


def test_the_listings_say_which_step_is_paused_and_until_when(
    client: TestClient, provider: FakeProvider
) -> None:
    assert client.get("/api/paused-steps").json() == []
    provider.error = TimeoutError()
    fail_times(3)

    [paused] = client.get("/api/paused-steps").json()

    assert paused["label"] == "Rating Matches"
    assert paused["until"] is not None
    assert paused["can_retry"] is True
