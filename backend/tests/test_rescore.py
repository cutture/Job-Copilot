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
    [call] = provider.received
    assert call["messages"][0]["content"] == rating.JUDGE_PROMPT
    task = json.loads(call["messages"][1]["content"])
    assert "posting" not in task and POSTING not in call["messages"][1]["content"]


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

    assert provider.received[0]["messages"][0]["content"] == rating.PROMPT
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
