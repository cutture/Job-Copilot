"""Claims without Evidence: Keep Anyway, undoing it, and Check again after adding Evidence.
Only model providers are faked."""

import json
from io import BytesIO
from typing import Any

import psycopg
from docx import Document
from fastapi.testclient import TestClient

from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import TOO_LONG, by_kind, judgement, texts
from tests.test_rating import add_evidence
from tests.test_review_and_record import ready_pack, review

LED = "Led a team of six engineers"


def view(client: TestClient, application_id: str) -> dict[str, Any]:
    found: dict[str, Any] = client.get(f"/api/applications/{application_id}").json()
    return found


def index_of(pack: dict[str, Any], text: str) -> int:
    # A Claim too long to check is listed cut short, so its start finds it.
    return next(i for i, r in enumerate(pack["removed_claims"]) if r["text"].startswith(text))


def removed(client: TestClient, application_id: str, text: str) -> str:
    pack = view(client, application_id)["pack"]
    return f"/api/applications/{application_id}/removed/{index_of(pack, text)}"


def lines(pack: dict[str, Any], role: int = 0) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = by_kind(pack["resume"])["experience"]["roles"][role]["lines"]
    return found


def decisions() -> list[tuple[str, bool]]:
    with psycopg.connect(TEST_DB) as conn:
        return [
            (row[0], row[1])
            for row in conn.execute("SELECT claim, kept FROM keep_decisions ORDER BY id")
        ]


def test_keeping_a_claim_puts_it_back_where_it_was_written_labelled_and_unsupported(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)

    response = client.post(f"{removed(client, application_id, LED)}/keep")

    assert response.status_code == 200, response.text
    after = response.json()
    pack = after["pack"]
    # Back between the lines it was written between, with no Evidence and labelled kept.
    assert texts(lines(pack)) == ["Shipped retrieval systems to production", LED]
    assert lines(pack)[1]["kept"] is True and lines(pack)[1]["evidence"] == []
    entry = pack["removed_claims"][index_of(pack, LED)]
    assert entry["kept"] is True
    # Changing a kept Claim clears the review tick, and the decision is recorded.
    assert after["reviewed"] is False
    assert decisions() == [(LED, True)]

    review(client, application_id)
    resume = client.get(f"/api/applications/{application_id}/resume.docx").content
    text = "\n".join(p.text for p in Document(BytesIO(resume)).paragraphs)
    assert LED in text
    assert "Kept" not in text


def test_removing_a_kept_claim_takes_it_out_again_and_is_recorded(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    client.post(f"{removed(client, application_id, LED)}/keep")
    review(client, application_id)

    after = client.delete(f"{removed(client, application_id, LED)}/keep").json()

    assert LED not in texts(lines(after["pack"]))
    assert after["pack"]["removed_claims"][index_of(after["pack"], LED)]["kept"] is False
    assert after["reviewed"] is False
    assert decisions() == [(LED, True), (LED, False)]


def test_only_some_removed_claims_can_be_kept(client: TestClient, provider: FakeProvider) -> None:
    application_id = ready_pack(client, provider)
    pack = view(client, application_id)["pack"]
    by_text = {r["text"][:40]: r for r in pack["removed_claims"]}

    assert by_text[LED]["cant_keep"] is None
    assert "too long" in by_text[TOO_LONG[:40]]["cant_keep"]
    line = by_text["Worked in a team of six engineers"]
    assert "job heading" in line["cant_keep"] and line["can_check"] is False
    assert client.post(f"{removed(client, application_id, TOO_LONG[:40])}/keep").status_code == 409


def test_a_line_removed_with_its_heading_can_be_kept_once_the_heading_is_back(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    heading = "Staff Engineer, Example Corp, 2010 to 2012"
    line = "Worked in a team of six engineers"
    assert client.post(f"{removed(client, application_id, line)}/keep").status_code == 409

    client.post(f"{removed(client, application_id, heading)}/keep")
    pack = client.post(f"{removed(client, application_id, line)}/keep").json()["pack"]

    roles = by_kind(pack["resume"])["experience"]["roles"]
    assert [role["heading"]["text"] for role in roles][1] == heading
    assert texts(lines(pack, 1)) == [line]


def test_check_again_brings_a_claim_back_once_verification_passes_on_new_evidence(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)
    new = add_evidence(client, "Ran Kubernetes clusters for Example Co's retrieval services")

    provider.tasks["verify"] = json.dumps({"statements": [judgement("s1", "invented")]})
    still = client.post(f"{removed(client, application_id, 'Kubernetes')}/check").json()
    assert "Kubernetes" not in texts(by_kind(still["pack"]["resume"])["skills"]["claims"])
    assert still["reviewed"] is True

    provider.tasks["verify"] = json.dumps({"statements": [judgement("s1", "reworded", new)]})
    back = client.post(f"{removed(client, application_id, 'Kubernetes')}/check").json()

    skills = by_kind(back["pack"]["resume"])["skills"]["claims"]
    assert texts(skills)[:2] == ["Python", "Kubernetes"]
    assert [ref["id"] for ref in skills[1]["evidence"]] == [new]
    assert "Kubernetes" not in texts(back["pack"]["removed_claims"])
    assert back["reviewed"] is False


def test_a_submitted_pack_stays_as_it_was_sent(client: TestClient, provider: FakeProvider) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)
    client.post(f"/api/applications/{application_id}/submitted")

    assert client.post(f"{removed(client, application_id, LED)}/keep").status_code == 409
    assert client.post(f"{removed(client, application_id, LED)}/check").status_code == 409


def test_a_pack_written_before_drafts_were_kept_says_how_to_keep_a_claim(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE application_packs SET draft = NULL")

    entry = view(client, application_id)["pack"]["removed_claims"][0]

    assert "Write a new Pack" in entry["cant_keep"] and entry["can_check"] is False
    assert client.post(f"{removed(client, application_id, entry['text'])}/keep").status_code == 409


def test_kept_claims_per_application_counts_totals_only(
    client: TestClient, provider: FakeProvider
) -> None:
    assert client.get("/api/kept-claims").json() == {"kept": 0, "applications": 0}
    application_id = ready_pack(client, provider)
    client.post(f"{removed(client, application_id, LED)}/keep")

    assert client.get("/api/kept-claims").json() == {"kept": 1, "applications": 1}
