"""Export: the Profile, Applications and Packs as readable files. Only providers are faked."""

import json
import zipfile
from io import BytesIO

import psycopg
from fastapi.testclient import TestClient

from job_copilot.api import app
from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import PYTHON
from tests.test_deletion import as_other_person, ready_application

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
    ready_application(client, provider)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE job_postings SET title = %s", (PLANTED_TITLE,))

    names = export(client).namelist()

    assert all(".." not in name and not name.startswith("/") for name in names)
    assert any("etc-passwd-Engineer" in name for name in names)
