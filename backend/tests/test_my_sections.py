"""A Pack's resume follows the person's own sections. Only model providers are faked."""

import json
from io import BytesIO
from typing import Any

import psycopg
from docx import Document
from fastapi.testclient import TestClient

from job_copilot import worker
from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import (
    EDUCATION,
    PYTHON,
    apply,
    by_kind,
    claim,
    judgement,
    rated_match,
    run_worker,
    texts,
)
from tests.test_profile import make_docx, upload

# The person's resume, as the reading reports it: their headings in their order.
THEIR_SECTIONS = [
    {"heading": "Profile", "kind": "summary"},
    {"heading": "Professional Skills", "kind": "skills", "grouped": True},
    {"heading": "Work History", "kind": "experience"},
    {"heading": "Personal Details", "kind": "other"},
    {"heading": "Education", "kind": "education"},
    {"heading": "Affiliations", "kind": "affiliations"},
]
PERSONAL = "Nationality: Examplian"
# Personal fields in other forms, and an honest line that only mentions a field's word.
ALSO_PERSONAL = ["DOB: 1 Jan 1990", "Marital: Single", "Citizenship: Examplian", "Born in 1990"]
HONEST = "BA in Religion, Example University"


def upload_resume(client: TestClient, provider: FakeProvider, sections: list[Any]) -> None:
    provider.text = json.dumps({"sections": sections, "items": ["Python Developer at Example Co"]})
    assert upload(client, "resume.docx", make_docx(["Sam Rivera", "Python"])).status_code == 201  # type: ignore[attr-defined]
    worker.run_once()


def stored_sections() -> Any:
    with psycopg.connect(TEST_DB) as conn:
        row = conn.execute("SELECT resume_sections FROM profiles").fetchone()
    return row[0] if row else None


def write_sections(provider: FakeProvider, ids: dict[str, int]) -> None:
    """A writer that fills every section kind, with traps, and Verification's judgements."""
    py, rag, team = ids["python"], ids["retrieval"], ids["team"]
    resume = {
        # Two sentences in one Claim, which are checked one by one.
        "summary": [
            claim(
                "Python developer who ships retrieval systems. Award-winning speaker at global "
                "conferences.",
                py,
                rag,
            ),
            claim(f"{PERSONAL}.", py),
        ],
        "skills": [
            {"group": claim("Retrieval", rag, py), "skills": [claim("Retrieval systems", rag)]},
            {"group": claim("Leadership"), "skills": [claim("Python", py)]},
            {"group": claim(PERSONAL, py), "skills": [claim("FastAPI", py)]},
            {"group": claim("Cloud", py), "skills": [claim("Kubernetes")]},
        ],
        "experience": [
            {"heading": claim(PYTHON, py), "bullets": [claim("Shipped retrieval systems", rag)]}
        ],
        "education": [claim(EDUCATION, 0), claim(HONEST, 0)],
        "affiliations": [
            claim("Member of a team of six engineers", team),
            *(claim(line, team) for line in ALSO_PERSONAL),
        ],
        "certifications": [claim("Certified Kubernetes Administrator")],
    }
    checked = [
        judgement("m0", "reworded", py, rag),
        judgement("m1", "invented"),
        judgement("g0", "reworded", rag, py),
        judgement("g0s0", "reworded", rag),
        judgement("g1", "invented"),
        judgement("g1s0", "reworded", py),
        judgement("g2s0", "reworded", py),
        judgement("g3", "reworded", py),
        judgement("g3s0", "invented"),
        judgement("e0", "reworded", py),
        judgement("e0b0", "reworded", rag),
        judgement("d0", "reworded", 0),
        judgement("d1", "reworded", 0),
        judgement("a0", "reworded", team),
        judgement("t0", "invented"),
        judgement("c0s0", "not_a_claim"),
    ]
    letter = {"paragraphs": [{"sentences": [claim("Dear team,")]}]}
    provider.tasks = {
        "resume": json.dumps(resume),
        "cover_letter": json.dumps(letter),
        "verify": json.dumps({"statements": checked}),
    }


def ready_pack(client: TestClient, provider: FakeProvider) -> dict[str, Any]:
    posting_id, ids = rated_match(client, provider)
    write_sections(provider, ids)
    application = apply(client, posting_id)
    run_worker()
    pack: dict[str, Any] = client.get(f"/api/applications/{application['id']}").json()["pack"]
    return {"id": application["id"], **pack}


def test_reading_a_resume_records_only_its_headings(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume(client, provider, THEIR_SECTIONS)

    # Mapped to known kinds in their order; "Personal Details" and anything else aren't kept.
    assert stored_sections() == [
        {"kind": "summary", "heading": "Profile", "grouped": False},
        {"kind": "skills", "heading": "Professional Skills", "grouped": True},
        {"kind": "experience", "heading": "Work History", "grouped": False},
        {"kind": "education", "heading": "Education", "grouped": False},
        {"kind": "affiliations", "heading": "Affiliations", "grouped": False},
    ]


def test_a_heading_naming_a_personal_field_gives_way_to_the_standard_one(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume(client, provider, [{"heading": "Personal Profile", "kind": "summary"}])

    assert stored_sections() == [{"kind": "summary", "heading": "Summary", "grouped": False}]


def test_a_reading_that_names_no_sections_still_reads_its_evidence(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.text = json.dumps(["Python Developer at Example Co"])
    upload(client, "resume.docx", make_docx(["Python"]))
    worker.run_once()

    assert stored_sections() == []
    assert client.get("/api/profile").json()["extraction_status"] == "done"


def test_a_pack_follows_the_persons_sections_order_and_headings(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume(client, provider, THEIR_SECTIONS)

    pack = ready_pack(client, provider)

    assert [(s["kind"], s["heading"]) for s in pack["resume"]["sections"]] == [
        ("summary", "Profile"),
        ("skills", "Professional Skills"),
        ("experience", "Work History"),
        ("education", "Education"),
        ("affiliations", "Affiliations"),
    ]


def test_the_summary_and_group_headings_are_checked_claim_by_claim(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume(client, provider, THEIR_SECTIONS)

    pack = ready_pack(client, provider)

    sections = by_kind(pack["resume"])
    assert texts(sections["summary"]["claims"]) == ["Python developer who ships retrieval systems."]
    skills = sections["skills"]
    assert [g["heading"]["text"] for g in skills["groups"]] == ["Retrieval"]
    # A skill whose group name was invented or personal stays, without the group.
    assert set(texts(skills["claims"])) == {"Python", "FastAPI"}
    removed = {r["text"]: r["kind"] for r in pack["removed_claims"]}
    assert removed["Award-winning speaker at global conferences."] == "invented"
    assert removed["Leadership"] == "invented"
    # A group name left with no skills under it goes too.
    assert removed["Cloud"] == "unchecked"


def test_a_group_whose_skills_lose_their_evidence_loses_its_name(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume(client, provider, THEIR_SECTIONS)
    pack = ready_pack(client, provider)
    retrieval = next(
        ref["id"]
        for g in by_kind(pack["resume"])["skills"]["groups"]
        for ref in g["claims"][0]["evidence"]
    )

    client.delete(f"/api/evidence/{retrieval}")

    after = client.get(f"/api/applications/{pack['id']}").json()["pack"]
    assert by_kind(after["resume"])["skills"]["groups"] == []
    assert "Retrieval" in {r["text"] for r in after["removed_claims"]}


def test_a_writer_answer_with_text_around_its_json_still_makes_a_pack(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    write_sections(provider, ids)
    provider.tasks["resume"] = f"Here is the resume:\n{provider.tasks['resume']}\nGood luck!"

    application = apply(client, posting_id)
    run_worker()

    pack = client.get(f"/api/applications/{application['id']}").json()["pack"]
    assert pack["status"] == "ready"


def test_with_no_upload_the_default_order_applies(
    client: TestClient, provider: FakeProvider
) -> None:
    pack = ready_pack(client, provider)

    # Summary, Skills, Experience, Education, Certifications; Affiliations wasn't asked for.
    assert [s["kind"] for s in pack["resume"]["sections"]] == [
        "summary",
        "skills",
        "experience",
        "education",
    ]
    assert "Certified Kubernetes Administrator" in {r["text"] for r in pack["removed_claims"]}


def test_personal_fields_never_reach_a_resume(client: TestClient, provider: FakeProvider) -> None:
    upload_resume(client, provider, THEIR_SECTIONS)
    pack = ready_pack(client, provider)
    base = f"/api/applications/{pack['id']}"
    client.put(f"{base}/review", json={"reviewed": True})

    for line in (PERSONAL, *ALSO_PERSONAL):
        assert line not in json.dumps(pack)
    assert HONEST in texts(by_kind(pack["resume"])["education"]["claims"])
    for pair in ("styled", "plain"):
        file = Document(BytesIO(client.get(f"{base}/resume.docx", params={"pair": pair}).content))
        written = "\n".join(p.text for p in file.paragraphs)
        assert not any(line in written for line in (PERSONAL, *ALSO_PERSONAL))


def test_both_pairs_render_the_summary_and_skill_groups_and_pass_the_ats_check(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume(client, provider, THEIR_SECTIONS)
    pack = ready_pack(client, provider)
    base = f"/api/applications/{pack['id']}"
    client.put(f"{base}/review", json={"reviewed": True})

    for pair in ("styled", "plain"):
        response = client.get(f"{base}/resume.docx", params={"pair": pair})
        assert response.status_code == 200, response.text
        text = [p.text for p in Document(BytesIO(response.content)).paragraphs]
        assert "Python developer who ships retrieval systems." in text
        assert (
            ("Retrieval" in text) if pair == "styled" else ("Retrieval: Retrieval systems" in text)
        )
