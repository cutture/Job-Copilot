"""Change Requests, Back to previous version, and kept Claims across versions. Only model
providers are faked."""

import json
from typing import Any

import psycopg
from fastapi.testclient import TestClient

from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import run_worker
from tests.test_keep_anyway import LED, removed
from tests.test_review_and_record import ready_pack, review

SHORTER = "Lead with my retrieval work and shorten the cover letter."
PHD = "Say I have a PhD in Machine Learning."


def ask(client: TestClient, application_id: str, request: str) -> Any:
    return client.post(f"/api/applications/{application_id}/changes", json={"request": request})


def tasks(provider: FakeProvider, name: str) -> list[dict[str, Any]]:
    """The JSON task of every call for this part of a Pack."""
    found = []
    for r in provider.received:
        try:
            found.append(json.loads(r["messages"][-1]["content"]))
        except json.JSONDecodeError:
            continue  # Filter and rating calls aren't JSON tasks.
    return [task for task in found if isinstance(task, dict) and task.get("task") == name]


def test_a_change_request_writes_a_new_version_with_it(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)

    response = ask(client, application_id, SHORTER)

    assert response.status_code == 202, response.text
    assert response.json()["pack"]["status"] == "generating"
    run_worker()
    view = client.get(f"/api/applications/{application_id}").json()
    pack = view["pack"]
    assert (pack["status"], pack["version"], pack["change_requests"]) == ("ready", 2, [SHORTER])
    assert pack["has_previous"] is True and pack["estimate_usd"] is not None
    # Regenerating clears the review tick.
    assert view["reviewed"] is False
    assert tasks(provider, "resume")[-1]["change_requests"] == [SHORTER]
    assert tasks(provider, "cover_letter")[-1]["change_requests"] == [SHORTER]


def test_verification_never_sees_a_change_request_so_its_facts_arent_evidence(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    provider.received.clear()

    ask(client, application_id, PHD)
    run_worker()

    verifying = [r for r in provider.received if '"task": "verify"' in r["messages"][-1]["content"]]
    assert verifying
    assert not any(PHD in m["content"] for r in verifying for m in r["messages"])
    pack = client.get(f"/api/applications/{application_id}").json()["pack"]
    assert "PhD" not in json.dumps([pack["resume"], pack["cover_letter"]])


def test_requests_add_up_and_back_to_previous_version_undoes_one_at_a_time(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    ask(client, application_id, SHORTER)
    run_worker()
    ask(client, application_id, "Make the summary warmer.")
    run_worker()
    assert tasks(provider, "resume")[-1]["change_requests"] == [
        SHORTER,
        "Make the summary warmer.",
    ]
    review(client, application_id)

    back = client.post(f"/api/applications/{application_id}/previous").json()

    assert (back["pack"]["version"], back["pack"]["change_requests"]) == (2, [SHORTER])
    assert back["reviewed"] is False
    first = client.post(f"/api/applications/{application_id}/previous").json()["pack"]
    assert (first["version"], first["change_requests"], first["has_previous"]) == (1, [], False)
    assert client.post(f"/api/applications/{application_id}/previous").status_code == 409


def test_going_back_while_a_version_is_written_cancels_it(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    ask(client, application_id, SHORTER)

    back = client.post(f"/api/applications/{application_id}/previous").json()
    run_worker()

    assert (back["pack"]["version"], back["pack"]["status"]) == (1, "ready")
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute("SELECT count(*) FROM application_packs").fetchone() == (1,)


def test_a_kept_claim_carries_over_only_if_the_new_version_still_has_it(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    client.post(f"{removed(client, application_id, LED)}/keep")

    ask(client, application_id, SHORTER)
    run_worker()

    pack = client.get(f"/api/applications/{application_id}").json()["pack"]
    entry = next(r for r in pack["removed_claims"] if r["text"] == LED)
    assert entry["kept"] is True
    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute(
            "SELECT version, claim_id, kept FROM keep_decisions ORDER BY id"
        ).fetchall() == [(1, "e0b1", True), (2, "e0b1", True)]

    # A writer that drops the line drops the kept Claim with it.
    resume = json.loads(provider.tasks["resume"])
    resume["experience"][0]["bullets"] = resume["experience"][0]["bullets"][:1]
    provider.tasks["resume"] = json.dumps(resume)
    ask(client, application_id, "Shorter, please.")
    run_worker()
    pack = client.get(f"/api/applications/{application_id}").json()["pack"]
    assert not any(r["kept"] for r in pack["removed_claims"])


def test_change_requests_are_checked_and_stop_once_submitted(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    assert ask(client, application_id, "   ").status_code == 422
    assert ask(client, application_id, "x" * 501).status_code == 422
    for n in range(5):
        assert ask(client, application_id, f"Change {n}").status_code == 202
        run_worker()
    assert ask(client, application_id, "One more").status_code == 409

    review(client, application_id)
    client.post(f"/api/applications/{application_id}/submitted")
    assert ask(client, application_id, SHORTER).status_code == 409
    assert client.post(f"/api/applications/{application_id}/previous").status_code == 409
