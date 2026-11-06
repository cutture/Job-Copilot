"""The styled pair: its layout, its accent colour and the ATS check, by opening the files."""

from io import BytesIO
from typing import Any

import pytest
from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml.ns import qn
from fastapi.testclient import TestClient

from job_copilot import ats, documents
from job_copilot.applications import Claim, CoverLetter, EvidenceRef, Resume, Role, Section
from job_copilot.documents import split_dates, styled_cover_letter_docx, styled_resume_docx
from tests.conftest import FakeProvider
from tests.test_application_pack import EDUCATION, apply, rated_match, run_worker, write
from tests.test_rating import set_profile
from tests.test_review_and_record import APP_LABELS, REMOVED

SOURCE = [EvidenceRef(text="Resume line the Claim came from", origin="self_reported")]
ROLE = "Python Developer, Example Co, Jan 2021 to present"


def claim(text: str) -> Claim:
    return Claim(text=text, evidence=SOURCE)


RESUME = Resume(
    sections=[
        Section(kind="skills", heading="Skills", claims=[claim("Python"), claim("FastAPI")]),
        Section(
            kind="experience",
            heading="Experience",
            roles=[Role(heading=claim(ROLE), lines=[claim("Shipped retrieval systems")])],
        ),
        Section(kind="education", heading="Education", claims=[claim("BSc Computer Science")]),
    ]
)
LINES = ["Sam Rivera", "sam@example.com", *(c.text for c in RESUME.all_claims())]


def colours(paragraph: Any) -> list[str | None]:
    return [str(run.font.color.rgb) if run.font.color.rgb else None for run in paragraph.runs]


def border_and_fill(paragraph: Any) -> tuple[str | None, str | None]:
    properties = paragraph._p.pPr
    bottom = properties.find(qn("w:pBdr")).find(qn("w:bottom"))
    shading = properties.find(qn("w:shd"))
    fill = shading.get(qn("w:fill")) if shading is not None else None
    return bottom.get(qn("w:color")), fill


def test_the_styled_resume_has_the_agreed_layout_and_reads_cleanly() -> None:
    content = styled_resume_docx(RESUME, "Sam Rivera", "sam@example.com", "teal")
    document = Document(BytesIO(content))
    paragraphs = document.paragraphs

    # Two-tone name, surname in the accent colour, and one contact line under it in the body.
    name, contact = paragraphs[0], paragraphs[1]
    assert [run.text for run in name.runs] == ["Sam ", "Rivera"]
    assert colours(name) == ["333333", "0F5E5E"]
    assert contact.text == "sam@example.com"
    assert border_and_fill(contact) == ("0F5E5E", None)
    # Accent headings on a light shaded band with a thin rule.
    headings = [p for p in paragraphs if p.text in ("Skills", "Experience", "Education")]
    assert [border_and_fill(h) for h in headings] == [("0F5E5E", "E5F1F1")] * 3
    assert all(h.runs[0].font.all_caps and colours(h) == ["0F5E5E"] for h in headings)
    # Skills as plain round bullets in two page columns, then back to one.
    skills = [p for p in paragraphs if p.text in ("Python", "FastAPI")]
    assert {p.style.name if p.style else None for p in skills} == {"List Bullet"}
    # Word leaves the count out for a single column.
    assert [s._sectPr.find(qn("w:cols")).get(qn("w:num"), "1") for s in document.sections] == [
        "1",
        "2",
        "1",
    ]
    # Right-aligned dates by tab stop.
    role = next(p for p in paragraphs if p.text.startswith("Python Developer"))
    assert role.text == "Python Developer, Example Co\tJan 2021 to present"
    assert role.paragraph_format.tab_stops[0].alignment == WD_TAB_ALIGNMENT.RIGHT
    # No blank lines, nothing an ATS would skip, and every line reads back in order.
    assert all(p.text.strip() for p in paragraphs)
    assert not document.tables and not document.inline_shapes
    assert ats.problems(content, LINES) == []
    assert "Resume line the Claim came from" not in "\n".join(p.text for p in paragraphs)


def test_each_accent_colour_is_dark_on_a_light_band() -> None:
    for accent, (text, band) in documents.ACCENTS.items():
        heading = next(
            p
            for p in Document(BytesIO(styled_resume_docx(RESUME, None, None, accent))).paragraphs
            if p.text == "Skills"
        )
        assert border_and_fill(heading) == (text, band)
        # Text is dark enough to read on its band: every channel well below the band's.
        assert all(int(text[i : i + 2], 16) < 0x80 for i in (0, 2, 4))


def test_the_styled_cover_letter_matches_the_name_contact_and_accent() -> None:
    letter = CoverLetter(paragraphs=[[claim("Dear team,")], [claim("I build."), claim("Thanks.")]])

    content = styled_cover_letter_docx(letter, "Sam Rivera", "sam@example.com", "burgundy")

    paragraphs = Document(BytesIO(content)).paragraphs
    assert colours(paragraphs[0]) == ["333333", "7A1F3D"]
    assert [p.text for p in paragraphs] == [
        "Sam Rivera",
        "sam@example.com",
        "Dear team,",
        "I build. Thanks.",
        "Sam Rivera",
    ]
    lines = ["Sam Rivera", "sam@example.com", "Dear team,", "I build.", "Thanks."]
    assert ats.problems(content, lines) == []


@pytest.mark.parametrize(
    ("heading", "split"),
    [
        (ROLE, ("Python Developer, Example Co", "Jan 2021 to present")),
        ("Analyst, Example Bank, 2015 – 2018", ("Analyst, Example Bank", "2015 – 2018")),
        ("Founder, Example Labs", ("Founder, Example Labs", None)),
        ("2019 to 2021", ("2019 to 2021", None)),
    ],
)
def test_a_roles_closing_date_range_moves_to_the_right_margin(
    heading: str, split: tuple[str, str | None]
) -> None:
    assert split_dates(heading) == split


def ready(client: TestClient, provider: FakeProvider, accent: str) -> str:
    posting_id, ids = rated_match(client, provider)
    set_profile(
        client,
        education=EDUCATION,
        name="Sam Rivera",
        contact="sam@example.com",
        accent_colour=accent,
    )
    write(provider, ids)
    application_id: str = apply(client, posting_id)["id"]
    run_worker()
    client.put(f"/api/applications/{application_id}/review", json={"reviewed": True})
    return application_id


def test_both_pairs_download_in_the_saved_accent_colour_and_named_apart(
    client: TestClient, provider: FakeProvider
) -> None:
    base = f"/api/applications/{ready(client, provider, 'gold')}"

    files = {
        (pair, which): client.get(f"{base}/{which}", params={"pair": pair})
        for pair in ("styled", "plain")
        for which in ("resume.docx", "cover-letter.docx")
    }

    assert {
        key: r.headers["content-disposition"].rsplit("Northwind-Labs-", 1)[1]
        for key, r in files.items()
    } == {
        ("styled", "resume.docx"): "Resume.docx",
        ("styled", "cover-letter.docx"): "Cover-letter.docx",
        ("plain", "resume.docx"): "Resume-plain.docx",
        ("plain", "cover-letter.docx"): "Cover-letter-plain.docx",
    }
    gold, band = documents.ACCENTS["gold"]
    for (pair, _), response in files.items():
        document = Document(BytesIO(response.content))
        paragraphs = document.paragraphs
        text = "\n".join(p.text for p in paragraphs)
        assert not document.tables and all(p.text.strip() for p in paragraphs)
        assert not [label for label in REMOVED + APP_LABELS if label in text]
        surname = colours(paragraphs[0])[-1]
        assert surname == (gold if pair == "styled" else None)
    styled = Document(BytesIO(files["styled", "resume.docx"].content))
    headings = [p for p in styled.paragraphs if p.text in ("Skills", "Experience", "Education")]
    assert [border_and_fill(h) for h in headings] == [(gold, band)] * 3
    role = next(p for p in styled.paragraphs if p.text.startswith("Python Developer"))
    assert role.paragraph_format.tab_stops[0].alignment == WD_TAB_ALIGNMENT.RIGHT
    assert [s._sectPr.find(qn("w:cols")).get(qn("w:num"), "1") for s in styled.sections] == [
        "1",
        "2",
        "1",
    ]


def test_a_file_that_fails_the_ats_check_is_refused_with_the_reason(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = f"/api/applications/{ready(client, provider, 'navy')}"

    # A deliberate exception to faking only providers and Sources: the renderer never writes a
    # file the check refuses, so a broken one is put in its place to reach the guard.
    def boxed_in(resume: Resume, *_: Any) -> bytes:
        document = Document()
        document.add_table(rows=1, cols=1).cell(0, 0).text = "Python"
        out = BytesIO()
        document.save(out)
        return out.getvalue()

    monkeypatch.setattr(documents, "styled_resume_docx", boxed_in)

    refused = client.get(f"{base}/resume.docx")

    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("This file didn't pass the ATS check")
    assert "It has a table" in refused.json()["detail"]
    assert refused.json()["detail"].endswith("Download the plain pair instead.")
    assert client.get(f"{base}/resume.docx", params={"pair": "plain"}).status_code == 200


def test_the_accent_colour_is_one_of_four(client: TestClient) -> None:
    refused = client.put("/api/profile", json={"accent_colour": "pink"})

    assert refused.status_code == 422
    assert client.get("/api/profile").json()["accent_colour"] == "navy"
