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


SHORT_GERMAN = "Wir suchen einen Entwickler für unser Team in Berlin und mit Erfahrung."
BILINGUAL = (
    "Senior AI Engineer. You will build retrieval systems for our customers and work with the "
    "platform team on the evaluation of models. Ingénieur IA principal. Vous allez construire des "
    "systèmes pour nos clients et travailler avec l'équipe sur l'évaluation des modèles."
)


def test_a_short_posting_not_in_english_is_set_aside_before_any_model(
    client: TestClient, provider: FakeProvider
) -> None:
    posting = filter_posting(client, provider, facts(), text=SHORT_GERMAN)

    assert posting["status"] == "filtered"
    assert provider.received == []


def test_a_bilingual_posting_that_includes_english_passes(
    client: TestClient, provider: FakeProvider
) -> None:
    posting = filter_posting(client, provider, facts(), text=BILINGUAL)

    assert posting["status"] == "received"


@pytest.mark.parametrize(
    ("preferred", "location", "status"),
    [
        (["US"], "San Francisco, California, United States", "received"),
        (["York"], "New York, New York, United States", "filtered"),
        (["San Francisco"], "San Francisco, California, United States", "received"),
    ],
)
def test_office_places_match_whole_place_names(
    client: TestClient, provider: FakeProvider, preferred: list[str], location: str, status: str
) -> None:
    prefer(client, location_places=preferred)

    posting = filter_posting(
        client, provider, facts(work_arrangement="on_site", locations=[location])
    )

    assert posting["status"] == status


@pytest.mark.parametrize("region", ["EU", "North America", "Europe"])
def test_a_remote_role_for_a_broad_region_is_never_hidden(
    client: TestClient, provider: FakeProvider, region: str
) -> None:
    prefer(client, location_places=["Germany"])

    posting = filter_posting(client, provider, facts(residence_required=[region]))

    assert posting["status"] == "received"


def test_no_ticked_arrangement_means_no_preference(
    client: TestClient, provider: FakeProvider
) -> None:
    prefer(client, location_arrangements=[])

    posting = filter_posting(client, provider, facts(work_arrangement="on_site"))

    assert posting["status"] == "received"


def test_small_format_slips_in_the_model_answer_are_accepted(
    client: TestClient, provider: FakeProvider
) -> None:
    prefer(client, min_salary=120_000, min_salary_currency="USD")
    answer = facts(
        title="T" * 600,
        posting_type="Contract",
        work_arrangement="Remote",
        locations=None,
        residence_required=None,
        salary_max="125,000",
        salary_currency="usd",
    )

    posting = filter_posting(client, provider, answer)

    assert posting["status"] == "received"
    assert posting["posting_type"] == "freelance"
    assert posting["title"] == "T" * 120


@pytest.mark.parametrize("salary", ["a lot", 0, -5])
def test_an_unreadable_or_zero_salary_skips_only_the_salary_check(
    client: TestClient, provider: FakeProvider, salary: object
) -> None:
    prefer(client, min_salary=120_000, min_salary_currency="USD")

    posting = filter_posting(client, provider, facts(salary_max=salary, salary_currency="USD"))

    assert (posting["status"], posting["salary_note"]) == ("received", None)


def test_planted_residence_text_cannot_fill_the_filter_reason(
    client: TestClient, provider: FakeProvider
) -> None:
    prefer(client, location_places=["US"])
    planted = ["Call +1 555 0100 now to claim your offer\x07 " + "x" * 300] * 10

    posting = filter_posting(client, provider, facts(residence_required=planted))

    assert posting["status"] == "filtered"
    assert len(posting["filter_reason"]) <= 200
    assert "\x07" not in posting["filter_reason"]
