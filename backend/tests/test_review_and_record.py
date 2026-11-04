"""Review, download, Submitted and Outcome journeys. Only model providers are faked."""

import json
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID

import psycopg
from docx import Document
from fastapi.testclient import TestClient

from job_copilot.api import app, current_user_id
from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import EDUCATION, apply, rated_match, run_worker, write
from tests.test_rating import set_profile

REMOVED = [
    "Kubernetes",
    "FastAPI",
    "Rust",
    "Led a team of six engineers",
    "Cut support costs by 40%",
    "Staff Engineer, Example Corp",
    "I bring 10 years of leadership.",
]
# Words that belong to the app's own screens, never to the person's files.
APP_LABELS = ["Evidence", "Removed", "Self-reported", "self_reported", "Claim", "Verification"]


def ready_pack(client: TestClient, provider: FakeProvider) -> str:
    posting_id, ids = rated_match(client, provider)
    set_profile(client, education=EDUCATION, name="Sam Rivera", contact="sam@example.com")
    write(provider, ids)
    application_id: str = apply(client, posting_id)["id"]
    run_worker()
    return application_id


def opened(content: bytes) -> str:
    document = Document(BytesIO(content))
    properties = document.core_properties
    return "\n".join([p.text for p in document.paragraphs] + [properties.author, properties.title])


def review(client: TestClient, application_id: str, reviewed: bool = True) -> dict[str, Any]:
    response = client.put(f"/api/applications/{application_id}/review", json={"reviewed": reviewed})
    assert response.status_code == 200, response.text
    view: dict[str, Any] = response.json()
    return view


def test_a_reviewed_pack_downloads_clean_files_then_is_submitted_and_gets_an_outcome(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    base = f"/api/applications/{application_id}"

    # Locked until reviewed.
    assert client.get(f"{base}/resume.docx").status_code == 409
    assert client.post(f"{base}/submitted").status_code == 409

    assert review(client, application_id)["reviewed"] is True
    resume = client.get(f"{base}/resume.docx")
    letter = client.get(f"{base}/cover-letter.docx")

    assert resume.status_code == letter.status_code == 200
    assert resume.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''Sam-Rivera-Senior-GenAI-Engineer-Northwind-Labs-Resume.docx"
    )
    assert letter.headers["content-disposition"].endswith("-Cover-letter.docx")
    for content in (resume.content, letter.content):
        text = opened(content)
        assert "Sam Rivera" in text
        for removed in REMOVED + APP_LABELS:
            assert removed not in text
    assert "Shipped retrieval systems to production" in opened(resume.content)
    assert "I shipped retrieval systems." in opened(letter.content)

    submitted = client.post(f"{base}/submitted").json()
    assert submitted["submitted_at"] is not None
    reported = client.put(f"{base}/outcome", json={"outcome": "interview"}).json()
    assert reported["outcome"] == "interview"

    [row] = client.get("/api/applications").json()
    assert (row["title"], row["source"], row["status"], row["outcome"]) == (
        "Senior GenAI Engineer, Northwind Labs",
        "Manual Source",
        "submitted",
        "interview",
    )
    assert row["submitted_at"] == submitted["submitted_at"]
    with psycopg.connect(TEST_DB) as conn:
        cost = conn.execute(
            "SELECT sum(cost_usd) FROM model_calls WHERE application_id = %s", (application_id,)
        ).fetchone()
    assert cost is not None and Decimal(row["cost_usd"]) == cost[0] > 0

    # The review stays once the Application is Submitted.
    assert client.put(f"{base}/review", json={"reviewed": False}).status_code == 409


def test_the_name_and_contact_line_never_reach_a_model(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)

    view = client.get(f"/api/applications/{application_id}").json()

    assert (view["name"], view["contact"]) == ("Sam Rivera", "sam@example.com")
    sent = json.dumps(provider.received)
    assert "Sam Rivera" not in sent and "sam@example.com" not in sent


def test_unticking_the_review_locks_downloads_again(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)

    assert review(client, application_id, reviewed=False)["reviewed"] is False

    base = f"/api/applications/{application_id}"
    assert client.get(f"{base}/cover-letter.docx").status_code == 409
    assert client.post(f"{base}/submitted").status_code == 409


def test_only_a_verified_pack_can_be_reviewed(client: TestClient, provider: FakeProvider) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    application_id = apply(client, posting_id)["id"]

    response = client.put(f"/api/applications/{application_id}/review", json={"reviewed": True})

    assert response.status_code == 409
    assert client.get("/api/applications").json()[0]["status"] == "generating"


def test_an_outcome_needs_submitted_and_is_one_of_four(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    base = f"/api/applications/{application_id}"

    assert client.put(f"{base}/outcome", json={"outcome": "offer"}).status_code == 409
    review(client, application_id)
    client.post(f"{base}/submitted")
    assert client.put(f"{base}/outcome", json={"outcome": "ghosted"}).status_code == 422
    for outcome in ("offer", "rejected", "no_response"):
        assert client.put(f"{base}/outcome", json={"outcome": outcome}).json()["outcome"] == outcome


def test_a_pack_without_a_name_still_downloads(client: TestClient, provider: FakeProvider) -> None:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    application_id = apply(client, posting_id)["id"]
    run_worker()

    assert review(client, application_id)["name"] is None
    resume = client.get(f"/api/applications/{application_id}/resume.docx")
    assert resume.headers["content-disposition"].endswith(
        "''Senior-GenAI-Engineer-Northwind-Labs-Resume.docx"
    )


def test_another_persons_application_cant_be_reviewed_downloaded_or_reported(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)
    other = UUID("00000000-0000-0000-0000-000000000002")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (other,))
    app.dependency_overrides[current_user_id] = lambda: other
    try:
        base = f"/api/applications/{application_id}"
        assert client.get(f"{base}/resume.docx").status_code == 404
        assert client.put(f"{base}/review", json={"reviewed": True}).status_code == 404
        assert client.post(f"{base}/submitted").status_code == 404
        assert client.put(f"{base}/outcome", json={"outcome": "offer"}).status_code == 404
        assert client.get("/api/applications").json() == []
    finally:
        app.dependency_overrides.clear()
