import io
import json
from typing import Any
from uuid import UUID

import psycopg
import pytest
from docx import Document
from fastapi.testclient import TestClient

from job_copilot import worker
from job_copilot.api import app, current_user_id
from job_copilot.profile import confirmed_evidence
from tests.conftest import TEST_DB, FakeProvider

USER = UUID("00000000-0000-0000-0000-000000000001")
RESUME_LINES = ["Sam Rivera", "Python Developer, Example Co, 2021 to present", "Built RAG apps"]
EXTRACTED = ["Python Developer at Example Co, 2021 to present", "Built RAG applications"]


def make_docx(lines: list[str]) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def make_pdf(lines: list[str]) -> bytes:
    text = "BT /F1 12 Tf 72 720 Td " + " 0 -16 Td ".join(f"({line}) Tj" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
    ]
    pdf = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    pdf += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return pdf.encode("latin-1")


def upload(client: TestClient, name: str, content: bytes) -> object:
    return client.post("/api/profile/resume", files={"file": (name, content)})


def evidence(client: TestClient) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = client.get("/api/profile").json()["evidence"]
    return items


def extract(client: TestClient, provider: FakeProvider, items: list[str]) -> None:
    provider.text = json.dumps(items)
    response = upload(client, "resume.docx", make_docx(RESUME_LINES))
    assert response.status_code == 201  # type: ignore[attr-defined]
    worker.run_once()


def test_a_new_profile_defaults_languages_to_english(client: TestClient) -> None:
    profile = client.get("/api/profile").json()

    assert profile["languages"] == ["English"]
    assert profile["evidence"] == []
    assert profile["resume_text"] is None


def test_a_docx_resume_is_read_and_its_evidence_is_proposed_by_an_eligible_model(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.text = json.dumps(EXTRACTED)

    response = client.post(
        "/api/profile/resume", files={"file": ("resume.docx", make_docx(RESUME_LINES))}
    )

    assert response.status_code == 201
    profile = client.get("/api/profile").json()
    assert "Python Developer, Example Co, 2021 to present" in profile["resume_text"]
    assert profile["extraction_status"] == "queued"

    worker.run_once()

    profile = client.get("/api/profile").json()
    assert profile["extraction_status"] == "done"
    assert [(e["text"], e["origin"], e["confirmed"]) for e in profile["evidence"]] == [
        (EXTRACTED[0], "resume", False),
        (EXTRACTED[1], "resume", False),
    ]
    assert provider.received[0]["model"] == "anthropic/claude-haiku-5-5"
    assert "Sam Rivera" in str(provider.received[0]["messages"])


def test_a_pdf_resume_is_read(client: TestClient) -> None:
    response = upload(client, "resume.pdf", make_pdf(RESUME_LINES))

    assert response.status_code == 201  # type: ignore[attr-defined]
    assert "Built RAG apps" in client.get("/api/profile").json()["resume_text"]


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("resume.txt", b"plain text", "PDF or DOCX"),
        ("resume.pdf", b"not really a pdf", "PDF or DOCX"),
        ("resume.pdf", make_pdf([]), "no text"),
    ],
)
def test_unreadable_uploads_are_refused_with_a_reason(
    client: TestClient, name: str, content: bytes, message: str
) -> None:
    response = upload(client, name, content)

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert message in response.json()["detail"]  # type: ignore[attr-defined]
    assert client.get("/api/profile").json()["resume_text"] is None


def test_an_oversized_upload_is_refused(client: TestClient) -> None:
    response = upload(client, "resume.pdf", b"%PDF-" + b"x" * 5_000_001)

    assert response.status_code == 413  # type: ignore[attr-defined]


def test_evidence_can_be_confirmed_corrected_and_deleted(
    client: TestClient, provider: FakeProvider
) -> None:
    extract(client, provider, EXTRACTED)
    first, second = evidence(client)

    assert client.patch(f"/api/evidence/{first['id']}", json={"confirmed": True}).status_code == 200
    corrected = client.patch(
        f"/api/evidence/{second['id']}", json={"text": "Built two RAG applications"}
    )
    assert corrected.status_code == 200
    assert {(e["text"], e["confirmed"]) for e in evidence(client)} == {
        (EXTRACTED[0], True),
        ("Built two RAG applications", True),
    }

    assert client.delete(f"/api/evidence/{first['id']}").status_code == 204
    assert [e["text"] for e in evidence(client)] == ["Built two RAG applications"]


def test_self_reported_evidence_is_added_confirmed_and_labelled(client: TestClient) -> None:
    created = client.post("/api/evidence", json={"text": "Ran Kubernetes services for 2 years"})

    assert created.status_code == 201
    assert [(e["text"], e["origin"], e["confirmed"]) for e in evidence(client)] == [
        ("Ran Kubernetes services for 2 years", "self_reported", True)
    ]


def test_blank_evidence_is_refused(client: TestClient) -> None:
    assert client.post("/api/evidence", json={"text": "  "}).status_code == 422


def test_only_confirmed_evidence_can_support_claims(
    client: TestClient, provider: FakeProvider
) -> None:
    extract(client, provider, EXTRACTED)
    first, _ = evidence(client)
    client.patch(f"/api/evidence/{first['id']}", json={"confirmed": True})
    client.post("/api/evidence", json={"text": "Mentored two interns"})

    assert {item.text for item in confirmed_evidence(USER)} == {
        EXTRACTED[0],
        "Mentored two interns",
    }


def test_a_new_upload_replaces_unconfirmed_resume_evidence_and_keeps_confirmed(
    client: TestClient, provider: FakeProvider
) -> None:
    extract(client, provider, EXTRACTED)
    first, _ = evidence(client)
    client.patch(f"/api/evidence/{first['id']}", json={"confirmed": True})

    extract(client, provider, ["Led a data team"])

    assert {e["text"] for e in evidence(client)} == {EXTRACTED[0], "Led a data team"}


def test_a_failed_extraction_is_shown_and_does_not_block_the_queue(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.error = RuntimeError("no credit")
    upload(client, "resume.docx", make_docx(RESUME_LINES))

    assert worker.run_once() is True

    profile = client.get("/api/profile").json()
    assert profile["extraction_status"] == "failed"
    assert profile["evidence"] == []
    assert worker.run_once() is False


def test_a_model_answer_that_is_not_a_list_fails_extraction(
    client: TestClient, provider: FakeProvider
) -> None:
    extract(client, provider, [])
    provider.text = "Sure! Here are the items: Python"
    upload(client, "resume.docx", make_docx(RESUME_LINES))
    worker.run_once()

    assert client.get("/api/profile").json()["extraction_status"] == "failed"


def test_proposed_items_are_cleaned_and_limited(client: TestClient, provider: FakeProvider) -> None:
    extract(client, provider, ["  Python\x07 developer ", "", "x" * 600] + ["item"] * 100)

    items = [e["text"] for e in evidence(client)]
    assert items[0] == "Python developer"
    assert len(items[1]) == 300
    assert len(items) == 60


def test_facts_and_preferences_are_saved_with_location_preference_separate(
    client: TestClient,
) -> None:
    saved = client.put(
        "/api/profile",
        json={
            "work_authorization": "Needs sponsorship",
            "lives_in": "Austin, US",
            "languages": ["English", "Spanish"],
            "seniority": "Senior",
            "roles": ["GenAI engineer"],
            "work_type": "employment",
            "min_salary": 120000,
            "location_arrangements": ["remote", "hybrid"],
            "location_places": ["US", "San Francisco"],
        },
    )

    assert saved.status_code == 200
    profile = client.get("/api/profile").json()
    assert profile["lives_in"] == "Austin, US"
    assert profile["location_places"] == ["US", "San Francisco"]
    assert profile["location_arrangements"] == ["remote", "hybrid"]
    assert profile["seniority"] == "Senior"
    assert profile["min_salary"] == 120000


@pytest.mark.parametrize(
    "change",
    [
        {"work_type": "anything"},
        {"seniority": "Wizard"},
        {"min_salary": -1},
        {"location_arrangements": ["moon"]},
    ],
)
def test_invalid_preferences_are_refused(client: TestClient, change: dict[str, object]) -> None:
    body = {"languages": ["English"], **change}

    assert client.put("/api/profile", json=body).status_code == 422


def test_a_person_cannot_change_another_persons_evidence(client: TestClient) -> None:
    created = client.post("/api/evidence", json={"text": "Mentored two interns"}).json()
    other = UUID("00000000-0000-0000-0000-000000000002")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (other,))

    app.dependency_overrides[current_user_id] = lambda: other
    try:
        assert client.get("/api/profile").json()["evidence"] == []
        assert client.delete(f"/api/evidence/{created['id']}").status_code == 404
        response = client.patch(f"/api/evidence/{created['id']}", json={"confirmed": True})
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()

    assert len(evidence(client)) == 1


def test_text_inside_docx_tables_is_read(client: TestClient) -> None:
    document = Document()
    document.add_paragraph("Sam Rivera")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Skills"
    table.cell(0, 1).text = "Python, FastAPI"
    out = io.BytesIO()
    document.save(out)

    upload(client, "resume.docx", out.getvalue())

    assert "Python, FastAPI" in client.get("/api/profile").json()["resume_text"]


def test_a_docx_that_expands_too_far_is_refused(client: TestClient) -> None:
    content = make_docx(["a" * 25_000_000])
    assert len(content) < 5_000_000

    response = upload(client, "resume.docx", content)

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert "too large" in response.json()["detail"]  # type: ignore[attr-defined]


def test_a_resume_with_too_much_text_is_refused(client: TestClient) -> None:
    response = upload(client, "resume.docx", make_docx(["word " * 30_000]))

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert "too long" in response.json()["detail"]  # type: ignore[attr-defined]


def test_uploading_twice_quickly_reads_the_resume_once(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.text = json.dumps(EXTRACTED)
    upload(client, "resume.docx", make_docx(RESUME_LINES))
    upload(client, "resume.docx", make_docx(RESUME_LINES))

    while worker.run_once():
        pass

    assert len(evidence(client)) == 2
    assert len(provider.received) == 1


def test_a_failed_reading_can_be_tried_again(client: TestClient, provider: FakeProvider) -> None:
    provider.error = RuntimeError("no credit")
    upload(client, "resume.docx", make_docx(RESUME_LINES))
    worker.run_once()
    provider.error = None
    provider.text = json.dumps(EXTRACTED)

    retried = client.post("/api/profile/resume/read-again")
    assert retried.status_code == 202
    assert client.get("/api/profile").json()["extraction_status"] == "queued"
    worker.run_once()

    assert len(evidence(client)) == 2


def test_reading_again_without_a_resume_is_refused(client: TestClient) -> None:
    assert client.post("/api/profile/resume/read-again").status_code == 409
