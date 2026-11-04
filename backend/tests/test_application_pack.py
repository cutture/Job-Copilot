"""Apply and Application Pack journeys. Only model providers are faked."""

import json
from typing import Any
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

from job_copilot import worker
from job_copilot.api import app, current_user_id
from tests.conftest import TEST_DB, FakeProvider
from tests.test_rating import POSTING, add_evidence, answer, rate_posting, set_profile, three_met

PYTHON = "Python Developer, Example Co, Jan 2021 to present"
RETRIEVAL = "Shipped Python retrieval systems to production"
TEAM = "Member of a team of six engineers"
EDUCATION = "BSc Computer Science, Example University"


def claim(text: str, *evidence: int) -> dict[str, Any]:
    return {"text": text, "evidence": list(evidence)}


def verdict(statement_id: str, name: str, *evidence: int) -> dict[str, Any]:
    return {"id": statement_id, "verdict": name, "evidence": list(evidence)}


def rated_match(client: TestClient, provider: FakeProvider) -> tuple[str, dict[str, int]]:
    set_profile(client, education=EDUCATION)
    ids = {
        "python": add_evidence(client, PYTHON),
        "retrieval": add_evidence(client, RETRIEVAL),
        "team": add_evidence(client, TEAM),
    }
    posting = rate_posting(client, provider, answer(*three_met(ids["retrieval"])))
    assert posting["match"]["band"] == "High"
    return posting["id"], ids


def write(provider: FakeProvider, ids: dict[str, int], **verdicts: str) -> None:
    """The writer's drafts, with planted traps, and Verification's verdicts on them."""
    py, rag, team = ids["python"], ids["retrieval"], ids["team"]
    resume = {
        "skills": [claim("Python", py), claim("Kubernetes"), claim("FastAPI", py)],
        "experience": [
            {
                "heading": claim(PYTHON, py),
                "bullets": [
                    claim("Shipped retrieval systems to production", rag),
                    claim("Led a team of six engineers", team),
                    claim("Cut support costs by 40%", rag),
                ],
            }
        ],
        "education": [claim(EDUCATION, 0)],
    }
    letter = {
        "paragraphs": [
            [claim("Dear Northwind Labs hiring team,")],
            [claim("I have 5 years of Python.", py), claim("I shipped retrieval systems.", rag)],
            [claim("I bring 10 years of leadership."), claim("Thank you.")],
            [claim("A fourth paragraph the letter has no room for.")],
        ]
    }
    checked = [
        verdict("s0", "reworded", py),
        verdict("s1", "not_a_claim"),
        # s2 gets no verdict.
        verdict("e0", "reworded", py),
        verdict("e0b0", "reworded", rag),
        verdict("e0b1", "stretched", team),
        verdict("d0", "reworded", 0),
        verdict("c0s0", "not_a_claim"),
        verdict("c1s0", "reworded", py),
        verdict("c1s1", "reworded", rag),
        verdict("c2s0", "not_a_claim"),
        verdict("c2s1", "not_a_claim"),
    ]
    provider.tasks = {
        "resume": json.dumps(resume),
        "cover_letter": json.dumps(letter),
        "verify": verdicts.get("verify", json.dumps({"statements": checked})),
    }


def run_worker() -> None:
    while worker.run_once():
        pass


def apply(client: TestClient, posting_id: str) -> dict[str, Any]:
    response = client.post("/api/applications", json={"job_posting_id": posting_id})
    assert response.status_code in (200, 201), response.text
    application: dict[str, Any] = response.json()
    return application


def texts(claims: list[dict[str, Any]]) -> list[str]:
    return [c["text"] for c in claims]


def test_apply_starts_an_application_and_a_verified_pack(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)

    started = apply(client, posting_id)

    assert (started["band"], started["source"], started["rubric_version"]) == (
        "High",
        "Manual Source",
        2,
    )
    assert started["pack"]["status"] == "generating"
    assert started["pack"]["resume"] is None
    with psycopg.connect(TEST_DB) as conn:
        saved = conn.execute("SELECT requirements FROM applications").fetchone()
    assert saved is not None and [r["requirement"] for r in saved[0]][:3] == [
        "Skill 0",
        "Skill 1",
        "Skill 2",
    ]

    run_worker()
    pack = client.get(f"/api/applications/{started['id']}").json()["pack"]

    assert (pack["status"], pack["version"], pack["model"]) == (
        "ready",
        1,
        "anthropic/claude-haiku-5-5",
    )
    resume = pack["resume"]
    assert list(resume) == ["skills", "experience", "education"]
    assert texts(resume["skills"]) == ["Python"]
    job = resume["experience"][0]
    assert job["heading"]["text"] == PYTHON
    assert texts(job["bullets"]) == ["Shipped retrieval systems to production"]
    assert texts(resume["education"]) == [EDUCATION]
    assert resume["skills"][0]["evidence"] == [{"text": PYTHON, "origin": "self_reported"}]
    assert resume["education"][0]["evidence"] == [
        {"text": f"Education: {EDUCATION}", "origin": "profile"}
    ]
    paragraphs = pack["cover_letter"]["paragraphs"]
    assert [texts(p) for p in paragraphs] == [
        ["Dear Northwind Labs hiring team,"],
        ["I have 5 years of Python.", "I shipped retrieval systems."],
        ["Thank you."],
    ]
    listed = {p["id"]: p for p in client.get("/api/job-postings").json()}
    assert listed[posting_id]["application_id"] == started["id"]


def test_verification_removes_stretched_and_invented_claims_and_lists_them(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    started = apply(client, posting_id)
    run_worker()

    removed = client.get(f"/api/applications/{started['id']}").json()["pack"]["removed_claims"]

    by_text = {r["text"]: r for r in removed}
    assert {text: r["kind"] for text, r in by_text.items()} == {
        # A resume line always states something about the person.
        "Kubernetes": "invented",
        "FastAPI": "unchecked",
        "Led a team of six engineers": "stretched",
        # Caught by code before the model saw it.
        "Cut support costs by 40%": "stretched",
        "I bring 10 years of leadership.": "invented",
    }
    assert by_text["Led a team of six engineers"]["reason"] == (
        f"It goes beyond what your Evidence says: “{TEAM}”"
    )
    assert by_text["Cut support costs by 40%"]["reason"] == "Your Evidence doesn't show 40%."
    for item in removed:
        assert item["next_step"].startswith("If it's true, add Evidence")


def test_each_part_is_its_own_call_and_verification_sees_no_writing_context(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    before = len(provider.received)
    apply(client, posting_id)
    run_worker()

    calls = provider.received[before:]
    tasks = [json.loads(c["messages"][-1]["content"])["task"] for c in calls]
    assert tasks == ["resume", "cover_letter", "verify"]
    assert {c["model"] for c in calls} == {"anthropic/claude-haiku-5-5"}
    verification = calls[2]
    sent = json.dumps(verification["messages"])
    assert POSTING[:40] not in sent
    assert calls[0]["messages"][0]["content"] not in sent
    assert calls[1]["messages"][0]["content"] not in sent


def test_a_failing_model_makes_the_pack_wait_with_a_warning_until_retried(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    started = apply(client, posting_id)
    provider.error = RuntimeError("provider down")
    run_worker()

    pack = client.get(f"/api/applications/{started['id']}").json()["pack"]
    assert pack["status"] == "waiting"
    assert pack["warning"].startswith("Our AI model isn't responding")
    assert pack["resume"] is None

    provider.error = None
    assert client.post(f"/api/applications/{started['id']}/retry").status_code == 202
    run_worker()

    assert client.get(f"/api/applications/{started['id']}").json()["pack"]["status"] == "ready"
    assert client.post(f"/api/applications/{started['id']}/retry").status_code == 409


def test_a_pack_whose_verification_fails_is_never_saved_or_shown(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids, verify="Everything looks true!")
    started = apply(client, posting_id)
    run_worker()

    pack = client.get(f"/api/applications/{started['id']}").json()["pack"]
    assert (pack["status"], pack["resume"], pack["cover_letter"]) == ("waiting", None, None)
    with psycopg.connect(TEST_DB) as conn:
        stored = conn.execute("SELECT resume, cover_letter FROM application_packs").fetchone()
    assert stored == (None, None)


def test_apply_again_opens_the_same_application(client: TestClient, provider: FakeProvider) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    first = apply(client, posting_id)

    again = client.post("/api/applications", json={"job_posting_id": posting_id})

    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    with psycopg.connect(TEST_DB) as conn:
        packs = conn.execute("SELECT count(*) FROM application_packs").fetchone()
    assert packs == (1,)


def test_apply_needs_a_rated_match(client: TestClient) -> None:
    response = client.post("/api/applications", json={"job_posting_id": str(uuid4())})

    assert response.status_code == 409


def test_each_person_sees_only_their_own_applications(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    started = apply(client, posting_id)
    other = UUID("00000000-0000-0000-0000-000000000002")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (other,))
    app.dependency_overrides[current_user_id] = lambda: other
    try:
        assert client.get(f"/api/applications/{started['id']}").status_code == 404
        assert client.post(f"/api/applications/{started['id']}/retry").status_code == 404
        assert (
            client.post("/api/applications", json={"job_posting_id": posting_id}).status_code == 409
        )
    finally:
        app.dependency_overrides.clear()
