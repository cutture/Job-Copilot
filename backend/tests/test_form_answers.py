"""Form answers: questions from Greenhouse or common fields, answered from Evidence under the
same Claim rules as the documents. Only model providers and Sources are faked."""

import json
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import form_answers, sources
from job_copilot.db import SEEDED_USER_ID
from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import RETRIEVAL
from tests.test_review_and_record import ready_pack

WHY = "Why do you want to join Example Labs?"
LEAD = "Describe your experience leading a team of 20."
FORM: dict[str, Any] = {
    "questions": [
        {
            "label": "First Name",
            "required": True,
            "fields": [{"name": "first_name", "type": "input_text"}],
        },
        {
            "label": "Last Name",
            "required": True,
            "fields": [{"name": "last_name", "type": "input_text"}],
        },
        {"label": "Email", "required": True, "fields": [{"name": "email", "type": "input_text"}]},
        {"label": "Phone", "fields": [{"name": "phone", "type": "input_text"}]},
        {
            "label": "Resume/CV",
            "required": True,
            "fields": [
                {"name": "resume", "type": "input_file"},
                {"name": "resume_text", "type": "textarea"},
            ],
        },
        {"label": "LinkedIn Profile", "fields": [{"name": "question_1", "type": "input_text"}]},
        {"label": WHY, "required": True, "fields": [{"name": "question_2", "type": "textarea"}]},
        {
            "label": "Are you legally authorized to work in the United Kingdom?",
            "required": True,
            "fields": [
                {
                    "name": "question_3",
                    "type": "multi_value_single_select",
                    "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}],
                }
            ],
        },
        {"label": "Tracking", "fields": [{"name": "gh_src", "type": "input_hidden"}]},
    ],
    "compliance": [
        {
            "type": "eeoc",
            "questions": [
                {
                    "label": "Gender",
                    "fields": [{"name": "gender", "type": "multi_value_single_select"}],
                },
                {
                    "label": "Veteran Status",
                    "fields": [{"name": "veteran_status", "type": "multi_value_single_select"}],
                },
            ],
        }
    ],
}


def test_each_greenhouse_question_gets_its_way_of_being_answered() -> None:
    found = [(q.question, q.kind, q.field) for q in form_answers.greenhouse_questions(FORM)]

    assert found == [
        ("First Name", "contact", "first_name"),
        ("Last Name", "contact", "last_name"),
        ("Email", "contact", "email"),
        ("Phone", "contact", "phone"),
        ("Resume/CV", "attach", None),
        ("LinkedIn Profile", "yourself", None),
        (WHY, "write", None),
        ("Are you legally authorized to work in the United Kingdom?", "yourself", None),
        ("Gender", "demographic", None),
        ("Veteran Status", "demographic", None),
    ]


def as_greenhouse(application_id: str) -> None:
    """Make the Application's posting one found on a Watchlist Greenhouse board."""
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        [watch_id] = conn.execute(
            """INSERT INTO watchlist (user_id, source, api_host, token, name)
               VALUES (%s, 'Greenhouse', 'boards-api.greenhouse.io', 'examplelabs', 'Example Labs')
               RETURNING id""",
            (SEEDED_USER_ID,),
        ).fetchone()  # type: ignore[misc]
        conn.execute(
            """UPDATE job_postings p SET source = 'Greenhouse', external_id = '4001',
                                         watchlist_id = %s
               FROM applications a WHERE a.job_posting_id = p.id AND a.id = %s""",
            (watch_id, application_id),
        )


@pytest.fixture
def greenhouse(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    fetched: list[str] = []

    def fetch(url: str) -> Any:
        fetched.append(url)
        return FORM

    monkeypatch.setattr(sources, "fetch_json", fetch)
    return fetched


def form(client: TestClient, application_id: str) -> Any:
    response = client.get(f"/api/applications/{application_id}/form-answers")
    assert response.status_code == 200, response.text
    return response.json()


def by_question(view: Any) -> dict[str, Any]:
    return {a["question"]: a for a in view["answers"]}


def evidence_ids(client: TestClient) -> dict[str, int]:
    return {e["text"]: e["id"] for e in client.get("/api/profile").json()["evidence"]}


def test_a_greenhouse_form_is_fetched_once_and_contact_fields_come_from_the_profile(
    client: TestClient, provider: FakeProvider, greenhouse: list[str]
) -> None:
    application_id = ready_pack(client, provider)
    as_greenhouse(application_id)

    view = form(client, application_id)
    form(client, application_id)

    assert greenhouse == [
        "https://boards-api.greenhouse.io/v1/boards/examplelabs/jobs/4001?questions=true"
    ]
    assert "Greenhouse form" in view["note"]
    answers = by_question(view)
    assert (answers["First Name"]["value"], answers["Last Name"]["value"]) == ("Sam", "Rivera")
    assert answers["Email"]["value"] == "sam@example.com"
    assert answers["Are you legally authorized to work in the United Kingdom?"]["options"] == [
        "Yes",
        "No",
    ]
    assert answers["Gender"]["kind"] == "demographic" and answers["Gender"]["sentences"] is None


def test_a_pasted_posting_or_an_unreachable_board_offers_the_common_fields(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    application_id = ready_pack(client, provider)
    pasted = form(client, application_id)
    assert [a["question"] for a in pasted["answers"]] == [q for q, _, _ in form_answers.COMMON]

    def down(url: str) -> Any:
        raise httpx.ConnectError("down")

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DELETE FROM form_answers")
    as_greenhouse(application_id)
    monkeypatch.setattr(sources, "fetch_json", down)

    unreachable = form(client, application_id)
    assert "Greenhouse didn't answer" in unreachable["note"]
    assert len(unreachable["answers"]) == len(form_answers.COMMON)


def test_answers_are_written_from_evidence_and_unsupported_sentences_are_taken_out(
    client: TestClient, provider: FakeProvider, greenhouse: list[str]
) -> None:
    application_id = ready_pack(client, provider)
    as_greenhouse(application_id)
    why = by_question(form(client, application_id))[WHY]["id"]
    ids = evidence_ids(client)
    provider.received.clear()
    provider.tasks["form_answers"] = json.dumps(
        {
            "answers": [
                {
                    "id": f"q{why}",
                    "sentences": [
                        {
                            "text": "I have shipped retrieval systems to production.",
                            "evidence": [ids[RETRIEVAL]],
                        },
                        {"text": "I led a team of 20 engineers.", "evidence": []},
                    ],
                }
            ]
        }
    )
    provider.tasks["verify"] = json.dumps(
        {
            "statements": [
                {"id": f"q{why}s0", "verdict": "reworded", "evidence": [ids[RETRIEVAL]]},
                {"id": f"q{why}s1", "verdict": "invented", "evidence": []},
            ]
        }
    )

    view = client.post(f"/api/applications/{application_id}/form-answers/prepare").json()

    answer = by_question(view)[WHY]
    assert [s["text"] for s in answer["sentences"]] == [
        "I have shipped retrieval systems to production."
    ]
    assert answer["sentences"][0]["evidence"][0]["text"] == RETRIEVAL
    assert [(r["text"], r["kind"]) for r in answer["removed"]] == [
        ("I led a team of 20 engineers.", "invented")
    ]
    # Only the free-text question is written; contact fields never reach a model.
    sent = json.dumps([r["messages"] for r in provider.received])
    assert "Sam Rivera" not in sent and "sam@example.com" not in sent
    assert "LinkedIn" not in sent and "authorized to work" not in sent and "Gender" not in sent


def test_a_pasted_question_is_answered_masked_and_sorted_like_the_forms_own(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    form(client, application_id)

    def answered(question: str) -> Any:
        return client.post(
            f"/api/applications/{application_id}/form-answers/questions",
            json={"question": question},
        )

    provider.received.clear()
    provider.tasks["form_answers"] = json.dumps({"answers": []})
    provider.tasks["verify"] = json.dumps({"statements": []})
    view = answered("Sam Rivera, why Python?").json()
    pasted = view["answers"][-1]
    assert pasted["question"] == "Sam Rivera, why Python?"
    # Nothing in the Evidence answered it, so it says so rather than inventing one.
    assert pasted["sentences"] == []
    assert "Sam Rivera" not in json.dumps([r["messages"] for r in provider.received])

    salary = answered("What are your salary expectations?").json()["answers"][-1]
    pronouns = answered("What are your pronouns?").json()["answers"][-1]
    assert (salary["kind"], pronouns["kind"]) == ("yourself", "demographic")
    assert answered("   ").status_code == 422

    kept = client.delete(f"/api/applications/{application_id}/form-answers/{salary['id']}")
    assert salary["question"] not in [a["question"] for a in kept.json()["answers"]]


def test_form_answers_go_with_their_application(client: TestClient, provider: FakeProvider) -> None:
    application_id = ready_pack(client, provider)
    form(client, application_id)

    client.delete(f"/api/applications/{application_id}")

    with psycopg.connect(TEST_DB) as conn:
        assert conn.execute("SELECT count(*) FROM form_answers").fetchone() == (0,)


def test_the_export_holds_each_applications_form_answers(
    client: TestClient, provider: FakeProvider
) -> None:
    import io
    import zipfile

    application_id = ready_pack(client, provider)
    form(client, application_id)

    with zipfile.ZipFile(io.BytesIO(client.get("/api/export").content)) as export:
        [name] = [n for n in export.namelist() if n.endswith("form-answers.json")]
        questions = [a["question"] for a in json.loads(export.read(name))]
    assert questions == [q for q, _, _ in form_answers.COMMON]


@pytest.mark.parametrize(
    "label",
    [
        "What's the name you'd prefer us to use throughout the interview process?",
        "It is important to us to create an accessible and inclusive interview process. Do you "
        "need any accommodations?",
        "Will you now or in the future require sponsorship for a visa?",
    ],
)
def test_personal_questions_on_real_forms_are_left_for_the_person(label: str) -> None:
    question = form_answers.classify(label, [{"name": "question_9", "type": "textarea"}])

    assert question.kind == "yourself"
