"""Rescore: judging a Match again against the Profile now, at the person's request, reusing the
Requirements already read from the posting. Only model providers are faked."""

import json
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import rating, worker
from tests.conftest import TEST_DB, FakeProvider
from tests.test_rating import POSTING, add_evidence, answer, rate_posting, set_profile, three_met
from tests.test_rating import requirement as rating_requirement


def judged(*results: str, evidence: int | None = None) -> str:
    """The judging step's answer: one Result for each saved Requirement, in order."""
    return json.dumps(
        {
            "requirements": [
                {"id": n, "result": result, "evidence": [evidence] if evidence else []}
                for n, result in enumerate(results)
            ]
        }
    )


def rated(client: TestClient, provider: FakeProvider) -> tuple[dict[str, Any], int]:
    set_profile(client)
    evidence_id = add_evidence(client)
    posting = rate_posting(client, provider, answer(*three_met(evidence_id)))
    assert posting["match"]["band"] == "High"
    return posting, evidence_id


def run_worker() -> None:
    while worker.run_once():
        pass


def listed(client: TestClient, posting_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        p for p in client.get("/api/job-postings").json() if p["id"] == posting_id
    )
    return found


def test_a_rescore_judges_the_saved_requirements_again_without_reading_the_posting(
    client: TestClient, provider: FakeProvider
) -> None:
    posting, evidence_id = rated(client, provider)
    client.delete(f"/api/evidence/{evidence_id}")
    assert listed(client, posting["id"])["match"]["profile_changed"] is True
    # Nothing rescores by itself.
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone() == (0,)

    provider.received.clear()
    provider.answers[rating.RATING_MODEL] = judged("missing", "missing", "missing")
    response = client.post("/api/rescore", json={"job_posting_ids": [posting["id"]]})
    assert response.status_code == 202
    assert listed(client, posting["id"])["rescoring"] is True
    run_worker()

    after = listed(client, posting["id"])
    match = after["match"]
    assert (after["rescoring"], match["profile_changed"]) == (False, False)
    assert (match["band"], match["previous_band"]) == ("Low", "High")
    # The same Requirements and quotes, judged again.
    assert [r["quote"] for r in match["requirements"] if r["profile_field"] != "languages"] == [
        r["quote"] for r in posting["match"]["requirements"] if r["profile_field"] != "languages"
    ]
    # Judging only: the posting itself never reaches a model again.
    assert POSTING not in json.dumps([r["messages"] for r in provider.received])


def test_an_applied_match_keeps_its_saved_rating(
    client: TestClient, provider: FakeProvider
) -> None:
    posting, _ = rated(client, provider)
    client.post("/api/applications", json={"job_posting_id": posting["id"]})

    estimate = client.post("/api/rescore/estimate", json={"job_posting_ids": [posting["id"]]})
    refused = client.post("/api/rescore", json={"job_posting_ids": [posting["id"]]})

    assert estimate.json()["count"] == 0
    assert refused.status_code == 409
    assert listed(client, posting["id"])["match"]["band"] == "High"


def test_the_estimate_comes_first_priced_at_the_model_that_would_take_it(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    posting, _ = rated(client, provider)
    ids = {"job_posting_ids": [posting["id"]]}

    paid = client.post("/api/rescore/estimate", json=ids).json()
    assert (paid["count"], paid["full_ratings"], paid["free"]) == (1, 0, False)
    assert paid["model"] == "Claude Haiku 5.5" and Decimal(paid["cost_usd"]) > 0

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    client.put("/api/model-settings/groq-zdr", json={"confirmed": True})
    free = client.post("/api/rescore/estimate", json=ids).json()
    assert free["free"] is True and Decimal(free["cost_usd"]) == 0
    # Asking for an estimate runs nothing.
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone() == (0,)


def test_a_match_rated_before_seniority_was_kept_is_rated_in_full_once(
    client: TestClient, provider: FakeProvider
) -> None:
    posting, evidence_id = rated(client, provider)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE matches SET seniority = NULL")

    estimate = client.post("/api/rescore/estimate", json={"job_posting_ids": [posting["id"]]})
    assert estimate.json()["full_ratings"] == 1

    provider.received.clear()
    provider.answers[rating.RATING_MODEL] = json.dumps(answer(*three_met(evidence_id)))
    client.post("/api/rescore", json={"job_posting_ids": [posting["id"]]})
    run_worker()

    match = listed(client, posting["id"])["match"]
    assert match["seniority"]["level"] == "Senior" and match["previous_band"] is None


def test_several_matches_rescore_together(client: TestClient, provider: FakeProvider) -> None:
    first, evidence_id = rated(client, provider)
    second = rate_posting(
        client, provider, answer(*three_met(evidence_id)), POSTING + " Kubernetes is a plus."
    )
    ids = [first["id"], second["id"]]
    assert client.post("/api/rescore/estimate", json={"job_posting_ids": ids}).json()["count"] == 2

    provider.answers[rating.RATING_MODEL] = judged("met", "met", "met", evidence=evidence_id)
    client.post("/api/rescore", json={"job_posting_ids": ids})
    run_worker()

    for posting_id in ids:
        match = listed(client, posting_id)["match"]
        # The Band didn't change, so there's no "was" to show.
        assert (match["band"], match["previous_band"]) == ("High", None)


def test_a_rescore_shows_as_running_until_its_saved_not_just_while_queued(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    posting, _ = rated(client, provider)
    seen: list[bool] = []
    judging = rating.rejudge

    def watched(*args: Any, **kwargs: Any) -> Any:
        # The worker has taken the job off the queue by now; the Match still says Rescoring.
        seen.append(listed(client, posting["id"])["rescoring"])
        return judging(*args, **kwargs)

    monkeypatch.setattr(rating, "rejudge", watched)
    provider.answers[rating.RATING_MODEL] = judged("met", "met", "met")
    client.post("/api/rescore", json={"job_posting_ids": [posting["id"]]})
    # Asking again while it's running queues nothing more.
    client.post("/api/rescore", json={"job_posting_ids": [posting["id"]]})
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone() == (1,)
    run_worker()

    assert seen == [True]
    assert listed(client, posting["id"])["rescoring"] is False


def test_a_failed_rescore_leaves_the_rating_and_stops_showing_as_running(
    client: TestClient, provider: FakeProvider
) -> None:
    posting, _ = rated(client, provider)
    provider.answers[rating.RATING_MODEL] = "not JSON"
    client.post("/api/rescore", json={"job_posting_ids": [posting["id"]]})
    run_worker()

    after = listed(client, posting["id"])
    assert (after["rescoring"], after["match"]["band"]) == (False, "High")


def test_a_posting_stating_no_seniority_is_judged_only_not_rated_in_full_again(
    client: TestClient, provider: FakeProvider
) -> None:
    set_profile(client)
    evidence_id = add_evidence(client)
    unstated = {"level": None, "quote": None, "firm_minimum": False}
    posting = rate_posting(client, provider, answer(*three_met(evidence_id), seniority=unstated))
    assert posting["match"]["seniority"] == {}

    estimate = client.post("/api/rescore/estimate", json={"job_posting_ids": [posting["id"]]})

    assert estimate.json()["full_ratings"] == 0


def test_a_rescore_judges_against_the_years_kept_with_the_requirement(
    client: TestClient, provider: FakeProvider
) -> None:
    set_profile(client)
    evidence_id = add_evidence(client)
    rating_answer = answer(
        rating_requirement(
            "Python",
            "5+ years of Python",
            evidence=[evidence_id],
            years_required=5,
            years_in_evidence=6,
        )
    )
    posting = rate_posting(client, provider, rating_answer)
    assert posting["match"]["requirements"][0]["years_required"] == 5

    # The judging answer shows 2 years and gives no years asked: the kept 5 still applies.
    provider.answers[rating.RATING_MODEL] = json.dumps(
        {
            "requirements": [
                {"id": 0, "result": "met", "evidence": [evidence_id], "years_in_evidence": 2}
            ]
        }
    )
    client.post("/api/rescore", json={"job_posting_ids": [posting["id"]]})
    run_worker()

    assert listed(client, posting["id"])["match"]["requirements"][0]["result"] == "partial"


def test_an_apply_between_asking_and_running_keeps_the_rating_and_clears_rescoring(
    client: TestClient, provider: FakeProvider
) -> None:
    posting, _ = rated(client, provider)
    provider.answers[rating.RATING_MODEL] = judged("missing", "missing", "missing")
    client.post("/api/rescore", json={"job_posting_ids": [posting["id"]]})
    client.post("/api/applications", json={"job_posting_id": posting["id"]})

    while worker.run_once():
        pass

    after = listed(client, posting["id"])
    assert (after["rescoring"], after["match"]["band"]) == (False, "High")


def test_the_estimate_names_a_paid_model_only_if_the_rescore_fits_under_the_cap(
    client: TestClient, provider: FakeProvider
) -> None:
    posting, _ = rated(client, provider)
    client.put("/api/model-settings/groq-zdr", json={"confirmed": True})
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        # Spent all but a hundredth of a cent of the cap.
        conn.execute(
            """INSERT INTO model_calls (user_id, model, step, input_tokens, output_tokens, cost_usd)
               SELECT id, 'seed', 'seed', 0, 0, monthly_cap_usd - 0.0001 FROM users
               WHERE id = '00000000-0000-0000-0000-000000000001'"""
        )

    estimate = client.post("/api/rescore/estimate", json={"job_posting_ids": [posting["id"]]})

    found = estimate.json()
    assert found["free"] is True and found["model"] != "Claude Haiku 5.5"
    assert found["ids"] == [posting["id"]]
