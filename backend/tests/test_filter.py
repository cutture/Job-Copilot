import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from job_copilot import worker
from tests.conftest import FakeProvider

ENGLISH = (
    "Senior GenAI Engineer at Northwind Labs. You will build and run retrieval systems for our "
    "customers, working with the platform team on the evaluation of large language models."
)
GERMAN = (
    "Wir suchen einen erfahrenen Entwickler für unser Team in Berlin. Sie arbeiten mit der "
    "Plattform und den Kunden an der Entwicklung von neuen Funktionen und Diensten für die Nutzer."
)
HINDI = (
    "हम अपनी टीम के लिए एक अनुभवी डेवलपर की तलाश कर रहे हैं जो नए उत्पाद बनाएगा और ग्राहकों के साथ काम करेगा।"
)


def facts(**changes: Any) -> str:
    base: dict[str, Any] = {
        "title": "Senior GenAI Engineer, Northwind Labs",
        "posting_type": "employment",
        "work_arrangement": "remote",
        "locations": [],
        "residence_required": [],
        "salary_max": None,
        "salary_currency": None,
    }
    return json.dumps({**base, **changes})


def prefer(client: TestClient, **changes: Any) -> None:
    body: dict[str, Any] = {
        "languages": ["English"],
        "work_type": "employment_and_freelance",
        "location_arrangements": ["remote", "hybrid", "on_site"],
        "location_places": [],
        **changes,
    }
    assert client.put("/api/profile", json=body).status_code == 200


def filter_posting(
    client: TestClient, provider: FakeProvider, answer: str, text: str = ENGLISH
) -> dict[str, Any]:
    provider.text = answer
    created = client.post("/api/job-postings", json={"text": text}).json()
    worker.run_once()
    posting: dict[str, Any] = next(
        p for p in client.get("/api/job-postings").json() if p["id"] == created["id"]
    )
    return posting


def test_a_posting_that_fits_passes_with_its_type_and_title(
    client: TestClient, provider: FakeProvider
) -> None:
    posting = filter_posting(client, provider, facts())

    assert posting["status"] == "received"
    assert posting["title"] == "Senior GenAI Engineer, Northwind Labs"
    assert posting["posting_type"] == "employment"
    assert posting["filter_reason"] is None


@pytest.mark.parametrize("text", [GERMAN, HINDI])
def test_a_posting_not_in_english_is_set_aside_before_any_model(
    client: TestClient, provider: FakeProvider, text: str
) -> None:
    posting = filter_posting(client, provider, facts(), text=text)

    assert posting["status"] == "filtered"
    assert posting["filter_reason"] == "Not written in English"
    assert provider.received == []


def test_filtered_postings_stay_listed_with_their_reason(
    client: TestClient, provider: FakeProvider
) -> None:
    filter_posting(client, provider, facts(), text=GERMAN)

    listed = client.get("/api/job-postings").json()
    assert [(p["status"], p["filter_reason"]) for p in listed] == [
        ("filtered", "Not written in English")
    ]


def test_contract_roles_are_freelance_and_respect_the_persons_work_type(
    client: TestClient, provider: FakeProvider
) -> None:
    prefer(client, work_type="employment")

    posting = filter_posting(client, provider, facts(posting_type="freelance"))

    assert posting["posting_type"] == "freelance"
    assert posting["status"] == "filtered"
    assert posting["filter_reason"] == "Freelance work, and you're looking for employment only"


def test_a_work_arrangement_outside_the_location_preference_is_filtered(
    client: TestClient, provider: FakeProvider
) -> None:
    prefer(client, location_arrangements=["remote"])

    posting = filter_posting(
        client, provider, facts(work_arrangement="on_site", locations=["Berlin, Germany"])
    )

    assert posting["status"] == "filtered"
    assert posting["filter_reason"] == "On-site, and your Location Preference doesn't include it"


@pytest.mark.parametrize(
    ("locations", "status"),
    [(["San Francisco, CA, USA"], "received"), (["Berlin, Germany"], "filtered")],
)
def test_office_roles_must_be_in_a_preferred_place(
    client: TestClient, provider: FakeProvider, locations: list[str], status: str
) -> None:
    prefer(client, location_places=["San Francisco"])

    posting = filter_posting(
        client, provider, facts(work_arrangement="hybrid", locations=locations)
    )

    assert posting["status"] == status


def test_office_roles_pass_when_no_places_are_set(
    client: TestClient, provider: FakeProvider
) -> None:
    prefer(client)

    posting = filter_posting(
        client, provider, facts(work_arrangement="on_site", locations=["Berlin, Germany"])
    )

    assert posting["status"] == "received"


@pytest.mark.parametrize(
    ("required", "status"),
    [([], "received"), (["United States"], "received"), (["United Kingdom"], "filtered")],
)
def test_remote_roles_are_hidden_only_for_a_residence_rule_outside_the_preference(
    client: TestClient, provider: FakeProvider, required: list[str], status: str
) -> None:
    prefer(client, location_places=["US"])

    posting = filter_posting(client, provider, facts(residence_required=required))

    assert posting["status"] == status
    if status == "filtered":
        assert (
            posting["filter_reason"] == "Remote, but requires living or working in United Kingdom"
        )


@pytest.mark.parametrize(
    ("salary_max", "currency", "status", "note"),
    [
        (130_000, "USD", "received", None),
        (108_000, "USD", "received", "Slightly below your minimum"),
        (100_000, "USD", "filtered", None),
        (None, None, "received", None),
        (100_000, "INR", "received", None),
    ],
)
def test_salary_passes_from_90_percent_of_the_minimum_in_the_same_currency(
    client: TestClient,
    provider: FakeProvider,
    salary_max: int | None,
    currency: str | None,
    status: str,
    note: str | None,
) -> None:
    prefer(client, min_salary=120_000, min_salary_currency="USD")

    posting = filter_posting(
        client, provider, facts(salary_max=salary_max, salary_currency=currency)
    )

    assert (posting["status"], posting["salary_note"]) == (status, note)
    if status == "filtered":
        assert posting["filter_reason"] == "Pay tops out below 90% of your minimum"


def test_filter_never_receives_personal_data_or_preferences(
    client: TestClient, provider: FakeProvider
) -> None:
    prefer(
        client,
        lives_in="Zanzibar City",
        work_authorization="Needs sponsorship everywhere",
        location_places=["Reykjavik"],
        min_salary=987_654,
        min_salary_currency="ISK",
    )
    client.post("/api/evidence", json={"text": "Mentored seventeen interns at Contoso"})

    filter_posting(client, provider, facts())

    sent = json.dumps(provider.received)
    assert provider.received[0]["model"] == "groq/openai/gpt-oss-20b"
    for private in ("Zanzibar", "sponsorship", "Reykjavik", "987654", "seventeen interns"):
        assert private not in sent


def test_an_unusable_model_answer_marks_the_posting_unavailable(
    client: TestClient, provider: FakeProvider
) -> None:
    posting = filter_posting(client, provider, "Looks like a great job!")

    assert posting["status"] == "model_unavailable"


def test_an_invalid_currency_preference_is_refused(client: TestClient) -> None:
    response = client.put(
        "/api/profile", json={"languages": ["English"], "min_salary_currency": "dollars"}
    )

    assert response.status_code == 422
