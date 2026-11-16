"""Inspecting a Pack's Claims and Requirement coverage, which belong to the app and never to
the files."""

from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient

from tests.conftest import FakeProvider
from tests.test_review_and_record import ready_pack, review


def test_a_ready_pack_carries_each_requirement_and_the_evidence_ids_its_claims_cite(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)

    pack = client.get(f"/api/applications/{application_id}").json()["pack"]

    requirements = pack["requirements"]
    assert requirements and all("result" in r and "evidence_ids" in r for r in requirements)
    cited = {
        ref["id"]
        for section in pack["resume"]["sections"]
        for role in section["roles"]
        for line in role["lines"]
        for ref in line["evidence"]
    }
    # Some Requirement rests on Evidence a resume Claim cites, so the panel can link them.
    assert any(cited & set(r["evidence_ids"]) for r in requirements)


def test_no_downloaded_file_underlines_anything(client: TestClient, provider: FakeProvider) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)

    for pair in ("styled", "plain"):
        for which in ("resume.docx", "cover-letter.docx"):
            content = client.get(
                f"/api/applications/{application_id}/{which}", params={"pair": pair}
            ).content
            # Claim underlining is only on screen: no text in the file is underlined, directly or
            # through its style.
            assert _underlined(content) == [], (pair, which)


def _underlined(content: bytes) -> list[str]:
    document = Document(BytesIO(content))
    paragraphs = list(document.paragraphs) + [
        p for table in document.tables for cell in table._cells for p in cell.paragraphs
    ]
    return [
        run.text
        for paragraph in paragraphs
        for run in paragraph.runs
        if run.text.strip()
        and (run.font.underline or run.style.font.underline or paragraph.style.font.underline)
    ]
