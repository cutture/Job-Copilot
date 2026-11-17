"""Both documents as PDF in both pairs, opened and checked like the DOCX files. Only model
providers are faked."""

import zipfile
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from job_copilot import ats, pdf
from job_copilot.applications import Resume
from tests.conftest import FakeProvider
from tests.test_photo import image
from tests.test_review_and_record import APP_LABELS, REMOVED, ready_pack, review

FILES = ("resume", "cover-letter")
PAIRS = ("styled", "plain")


def text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


def docx_words(content: bytes) -> list[str]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        body = archive.read("word/document.xml").decode("utf-8")
    return [w for paragraph in ats._paragraphs(body) for w in paragraph]


def get(client: TestClient, application_id: str, name: str, pair: str) -> Any:
    return client.get(f"/api/applications/{application_id}/{name}", params={"pair": pair})


def test_both_documents_download_as_pdf_named_and_clean_in_both_pairs(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    assert get(client, application_id, "resume.pdf", "styled").status_code == 409
    review(client, application_id)

    for pair in PAIRS:
        for which in FILES:
            response = get(client, application_id, f"{which}.pdf", pair)
            assert response.status_code == 200, (pair, which, response.text)
            assert response.headers["content-type"] == "application/pdf"
            ending = ("Resume" if which == "resume" else "Cover-letter") + (
                "-plain.pdf" if pair == "plain" else ".pdf"
            )
            assert response.headers["content-disposition"] == (
                "attachment; filename*=UTF-8''Sam-Rivera-Senior-GenAI-Engineer-Northwind-Labs-"
                + ending
            )
            read = text(response.content)
            assert "Sam Rivera" in read
            for absent in REMOVED + APP_LABELS:
                assert absent not in read, (pair, which, absent)
            metadata = PdfReader(BytesIO(response.content)).metadata
            assert metadata is not None and metadata.author == "Sam Rivera"
            assert not metadata.creator and not metadata.producer


def test_each_pdf_reads_as_its_docx_does(client: TestClient, provider: FakeProvider) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)

    for pair in PAIRS:
        for which in FILES:
            as_pdf = get(client, application_id, f"{which}.pdf", pair).content
            as_docx = get(client, application_id, f"{which}.docx", pair).content
            # The same words in the same order: what the page previews is what downloads.
            assert ats._words(text(as_pdf)) == docx_words(as_docx), (pair, which)


def test_the_styled_resume_pdf_alone_has_the_round_photo(
    client: TestClient, provider: FakeProvider
) -> None:
    application_id = ready_pack(client, provider)
    assert client.post("/api/profile/photo", files={"file": ("me.png", image())}).status_code == 200
    review(client, application_id)

    def pictures(name: str, pair: str) -> int:
        content = get(client, application_id, name, pair).content
        return sum(len(page.images) for page in PdfReader(BytesIO(content)).pages)

    assert pictures("resume.pdf", "styled") == 1
    assert pictures("resume.pdf", "plain") == 0
    assert pictures("cover-letter.pdf", "styled") == 0


def test_the_photo_is_cropped_round_with_clear_corners() -> None:
    with Image.open(BytesIO(pdf.round_photo(image(size=(300, 360))))) as round_:
        assert round_.size == (300, 300) and round_.mode == "RGBA"
        assert round_.getpixel((0, 0))[3] == 0  # type: ignore[index]
        assert round_.getpixel((150, 150))[3] == 255  # type: ignore[index]


def test_a_pdf_that_fails_the_ats_check_is_refused_with_the_reason(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    application_id = ready_pack(client, provider)
    review(client, application_id)

    # A deliberate exception to faking only providers: the renderer never writes a file the
    # check refuses, so one missing its Skills is put in its place to reach the guard.
    drawn = pdf.styled_resume_pdf

    def without_skills(resume: Resume, *rest: Any) -> bytes:
        kept = [s for s in resume.sections if s.kind != "skills"]
        return drawn(Resume(sections=kept), *rest)

    monkeypatch.setattr(pdf, "styled_resume_pdf", without_skills)

    refused = get(client, application_id, "resume.pdf", "styled")

    assert refused.status_code == 409
    assert "doesn't read back" in refused.json()["detail"]
    assert refused.json()["detail"].endswith("Download the plain pair instead.")
