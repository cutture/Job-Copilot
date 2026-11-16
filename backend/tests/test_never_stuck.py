"""A model failure never leaves the person stuck: the failure message, and submitting with their
own resume when there's no ready Application Pack."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import FakeProvider
from tests.test_application_pack import apply, rated_match, run_worker, write


def waiting_pack(client: TestClient, provider: FakeProvider) -> str:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    started = apply(client, posting_id)
    provider.error = RuntimeError("provider down")
    run_worker()
    provider.error = None
    application_id: str = started["id"]
    return application_id


def row(client: TestClient, application_id: str) -> Any:
    return next(r for r in client.get("/api/applications").json() if r["id"] == application_id)


def test_a_waiting_pack_says_what_happened_and_every_way_forward(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = waiting_pack(client, provider)

    warning = client.get(f"/api/applications/{application_id}").json()["pack"]["warning"]

    assert warning.startswith(
        "We couldn't write this Application Pack. Our AI models aren't responding right now: "
    )
    assert "Your Job Posting is saved, and everything else still works." in warning
    assert warning.endswith(
        "You can retry, check your model settings, or apply with your own resume and mark it as "
        "Submitted."
    )


def test_an_application_with_a_waiting_pack_can_be_submitted_with_your_own_resume(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = waiting_pack(client, provider)

    response = client.post(f"/api/applications/{application_id}/submitted")

    assert response.status_code == 200
    view = response.json()
    assert (view["submitted_at"] is not None, view["pack"]) == (True, None)
    listed = row(client, application_id)
    assert (listed["status"], listed["own_resume"]) == ("submitted", True)


def test_an_application_with_no_pack_can_be_submitted(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = waiting_pack(client, provider)
    client.delete(f"/api/applications/{application_id}/pack")

    assert client.post(f"/api/applications/{application_id}/submitted").status_code == 200
    assert row(client, application_id)["own_resume"] is True


def test_a_ready_pack_still_needs_its_review_before_submitting(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = waiting_pack(client, provider)
    client.post(f"/api/applications/{application_id}/retry")
    run_worker()

    assert client.post(f"/api/applications/{application_id}/submitted").status_code == 409
    client.put(f"/api/applications/{application_id}/review", json={"reviewed": True})
    assert client.post(f"/api/applications/{application_id}/submitted").status_code == 200
    assert row(client, application_id)["own_resume"] is False
