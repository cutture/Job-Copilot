"""Export: the Profile, Applications and Packs as readable files. Only providers are faked."""

import json
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient

from job_copilot import worker
from job_copilot.api import app
from job_copilot.applications import Claim, CoverLetter, Group, Resume, Section
from job_copilot.export import Signature, cover_letter_text, resume_text
from job_copilot.filter import FILTER_MODEL
from job_copilot.rating import RATING_MODEL
from tests.conftest import FakeProvider
from tests.test_application_pack import PYTHON, apply
from tests.test_deletion import as_other_person, ready_application
from tests.test_filter import facts
from tests.test_rating import POSTING, add_evidence, answer, set_profile, three_met

PLANTED_TITLE = "../../etc/passwd Engineer"


def export(client: TestClient) -> zipfile.ZipFile:
    response = client.get("/api/export")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    return zipfile.ZipFile(BytesIO(response.content))


def test_the_export_holds_readable_files_of_the_profile_applications_and_packs(
    client: TestClient, provider: FakeProvider
) -> None:
    _, application_id = ready_application(client, provider)

    files = export(client)

    names = files.namelist()
    assert "README.txt" in names
    profile = json.loads(files.read("profile.json"))
    assert PYTHON in [item["text"] for item in profile["evidence"]]
    folder = next(n.rsplit("/", 1)[0] for n in names if n.endswith("application.json"))
    application = json.loads(files.read(f"{folder}/application.json"))
    assert application["id"] == application_id
    assert application["posting"]
    pack = json.loads(files.read(f"{folder}/pack-v1.json"))
    assert pack["status"] == "ready"
    resume = files.read(f"{folder}/resume-v1.md").decode()
    assert PYTHON in resume
    assert "Removed" not in resume
    assert files.read(f"{folder}/cover-letter-v1.md").decode().strip()


def test_the_export_is_only_the_persons_own(client: TestClient, provider: FakeProvider) -> None:
    ready_application(client, provider)
    try:
        as_other_person()

        files = export(client)

        assert not [n for n in files.namelist() if n.startswith("applications/")]
        assert json.loads(files.read("profile.json"))["evidence"] == []
        assert PYTHON.encode() not in b"".join(files.read(n) for n in files.namelist())
    finally:
        app.dependency_overrides.clear()


def test_file_names_come_only_from_safe_characters(
    client: TestClient, provider: FakeProvider
) -> None:
    # A posting's title is untrusted: whatever it says, it can't name a path in the zip.
    set_profile(client)
    evidence_id = add_evidence(client)
    provider.answers = {
        FILTER_MODEL: facts(title=PLANTED_TITLE),
        RATING_MODEL: json.dumps(answer(*three_met(evidence_id))),
    }
    posting = client.post("/api/job-postings", json={"text": POSTING}).json()
    while worker.run_once():
        pass
    apply(client, posting["id"])

    names = export(client).namelist()

    assert all(".." not in name and not name.startswith("/") for name in names)
    assert any("etc-passwd-Engineer" in name for name in names)


def test_a_person_with_no_applications_still_gets_their_profile(client: TestClient) -> None:
    files = export(client)

    assert sorted(files.namelist()) == ["README.txt", "profile.json"]
    assert json.loads(files.read("profile.json"))["evidence"] == []


def test_the_text_files_are_laid_out_like_the_plain_pair() -> None:
    signature = Signature("Sam Rivera", "sam@example.com")
    skills = Claim(text="Python", evidence=[])
    resume = Resume(
        sections=[
            Section(kind="summary", heading="Profile", claims=[claim("Ships retrieval.")]),
            Section(
                kind="skills",
                heading="Skills",
                claims=[skills, claim("SQL")],
                groups=[Group(heading=claim("Cloud"), claims=[claim("Terraform")])],
            ),
            Section(kind="custom", heading="Open Source", claims=[claim("Maintains a library")]),
        ]
    )
    letter = CoverLetter(paragraphs=[[claim("Dear team,")], [claim("I build."), claim("I ship.")]])

    assert resume_text(resume, signature).splitlines() == [
        "# Sam Rivera",
        "sam@example.com",
        "",
        "## Profile",
        "Ships retrieval.",
        "",
        "## Skills",
        "Python, SQL",
        "**Cloud:** Terraform",
        "",
        "## Open Source",
        "- Maintains a library",
    ]
    assert cover_letter_text(letter, signature).split("\n\n") == [
        "# Sam Rivera\nsam@example.com",
        "Dear team,",
        "I build. I ship.",
        "Sam Rivera\n",
    ]


def claim(text: str) -> Claim:
    return Claim(text=text, evidence=[])
