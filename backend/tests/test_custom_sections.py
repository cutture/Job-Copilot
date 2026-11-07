"""Custom sections: headings the person names, filled only with verified Claims."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from job_copilot.profile import heading_refusal
from tests.conftest import FakeProvider
from tests.test_application_pack import apply, by_kind, claim, judgement, rated_match, run_worker
from tests.test_my_sections import THEIR_SECTIONS, upload_resume, write_sections


def custom_sections(client: TestClient) -> Any:
    return client.get("/api/profile").json()["custom_sections"]


def save_custom(client: TestClient, headings: list[str]) -> Any:
    return client.put("/api/profile", json={"custom_sections": headings})


def pack_with_custom(client: TestClient, provider: FakeProvider, heading: str) -> dict[str, Any]:
    """A Pack with a custom section the person added in their Profile, whose writer fills it with
    one true and one invented line."""
    posting_id, ids = rated_match(client, provider)
    # Saved after the rating's Profile, since saving a Profile replaces every field.
    client.put(
        "/api/profile", json={**client.get("/api/profile").json(), "custom_sections": [heading]}
    )
    write_sections(provider, ids)
    resume = json.loads(provider.tasks["resume"])
    resume["custom0"] = [
        claim("Maintains an open-source retrieval library", ids["retrieval"]),
        claim("Keynote speaker at ten conferences"),
    ]
    checked = json.loads(provider.tasks["verify"])
    checked["statements"] += [
        judgement("u0l0", "reworded", ids["retrieval"]),
        judgement("u0l1", "invented"),
    ]
    provider.tasks["resume"] = json.dumps(resume)
    provider.tasks["verify"] = json.dumps(checked)
    application = apply(client, posting_id)
    run_worker()
    pack: dict[str, Any] = client.get(f"/api/applications/{application['id']}").json()["pack"]
    return pack


def test_an_unmapped_heading_from_a_resume_becomes_a_custom_section(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume(
        client,
        provider,
        [*THEIR_SECTIONS, {"heading": "Open Source", "kind": "other"}],
    )

    # "Personal Details" is unmapped too, but names a personal field, so it isn't kept.
    assert custom_sections(client) == ["Open Source"]


def test_a_new_upload_adds_its_headings_and_keeps_the_persons_own(
    client: TestClient, provider: FakeProvider
) -> None:
    save_custom(client, ["Volunteering"])

    upload_resume(
        client,
        provider,
        [{"heading": "volunteering", "kind": "other"}, {"heading": "Open Source", "kind": "other"}],
    )

    assert custom_sections(client) == ["Volunteering", "Open Source"]


def test_a_removed_section_stays_removed_when_the_same_file_is_read_again(
    client: TestClient, provider: FakeProvider
) -> None:
    sections = [{"heading": "Open Source", "kind": "other"}, {"heading": "Talks", "kind": "other"}]
    upload_resume(client, provider, sections)
    save_custom(client, ["Talks"])

    upload_resume(client, provider, [*sections, {"heading": "Mentoring", "kind": "other"}])

    assert custom_sections(client) == ["Talks", "Mentoring"]


def test_a_heading_from_a_resume_that_cant_be_used_isnt_kept(
    client: TestClient, provider: FakeProvider
) -> None:
    upload_resume(
        client,
        provider,
        [
            {"heading": "Talks: www.example.com", "kind": "other"},
            {"heading": "Personal Information", "kind": "other"},
            {"heading": "Personal Projects", "kind": "other"},
        ],
    )

    assert custom_sections(client) == ["Personal Projects"]


@pytest.mark.parametrize(
    "heading",
    [
        "Personal Projects",
        "Personal Interests",
        "Publications 2019-2024",
        "Awards (2020 - 2023)",
        "ASP.NET Projects",
        "Grad.in Physics",
        "Projects @ Google",
        "Node.js Projects",
        "Talks & Workshops",
        "AI/ML Research",
    ],
)
def test_an_honest_heading_is_never_refused(heading: str) -> None:
    assert heading_refusal(heading) is None


def test_a_person_can_add_rename_and_remove_custom_sections(client: TestClient) -> None:
    assert save_custom(client, ["Volunteering", "Open Source"]).status_code == 200
    assert save_custom(client, ["Community Work", "Open Source"]).status_code == 200
    assert save_custom(client, ["Open Source"]).status_code == 200

    assert custom_sections(client) == ["Open Source"]


@pytest.mark.parametrize(
    ("heading", "reason"),
    [
        ("A" * 41, "at most 40 characters"),
        ("Portfolio: www.example.com", "a link or contact details"),
        ("https://example.com/me", "a link or contact details"),
        ("Write to sam@example.com", "a link or contact details"),
        ("Call +1 555 010 0199", "a link or contact details"),
        ("linkedin/in/sam", "a link or contact details"),
        ("Personal Details", "a personal field"),
    ],
)
def test_a_heading_too_long_or_with_a_link_contact_or_personal_field_is_refused(
    client: TestClient, heading: str, reason: str
) -> None:
    refused = save_custom(client, [heading])

    assert refused.status_code == 422
    assert reason in refused.json()["detail"]
    assert custom_sections(client) == []


def test_a_profile_added_section_comes_after_the_standard_ones_with_only_verified_claims(
    client: TestClient, provider: FakeProvider
) -> None:
    pack = pack_with_custom(client, provider, "Open Source")

    sections = pack["resume"]["sections"]
    assert sections[-1]["kind"] == "custom"
    assert sections[-1]["heading"] == "Open Source"
    assert [c["text"] for c in sections[-1]["claims"]] == [
        "Maintains an open-source retrieval library"
    ]
    assert {s["kind"] for s in sections[:-1]} >= {"skills", "experience", "education"}
    removed = {r["text"]: r["kind"] for r in pack["removed_claims"]}
    assert removed["Keynote speaker at ten conferences"] == "invented"
    assert "custom" in by_kind(pack["resume"])
