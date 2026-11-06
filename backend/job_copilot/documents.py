"""The document renderer: DOCX files of a verified Application Pack, in two pairs.

It takes only the saved documents, which hold verified Claims and no Removed Claims, and writes
only their text: no Evidence, labels, tables, text boxes, headers, footers or images. Both pairs
are one column, with the resume's sections in the order the Pack holds them.

- The styled pair, the default: a two-tone name, one contact line under it, accent headings on a
  light shaded band with a thin rule, right-aligned dates and Skills in two page columns.
- The plain pair: the same text with no styling, for portals that choke on any.

Every file passes the ATS parsing check before it can be downloaded.
"""

import re
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph
from fastapi import APIRouter, HTTPException, Response

from job_copilot import ats
from job_copilot.applications import CoverLetter, Resume, check_reviewed, latest_pack
from job_copilot.db import UserId, connect

router = APIRouter()

MAX_FILENAME_PART = 60
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
Style = Literal["styled", "plain"]
# Each accent colour: its text colour, and the light band behind headings. Text stays dark on
# light, so every pairing keeps its contrast.
ACCENTS = {
    "navy": ("1F3A5F", "EAF0F6"),
    "teal": ("0F5E5E", "E5F1F1"),
    "burgundy": ("7A1F3D", "F6EAEE"),
    "gold": ("7A5C10", "F6F0E0"),
}
DARK = RGBColor(0x33, 0x33, 0x33)
# A date range closing a role's heading, such as "Jan 2021 to present", set at the right margin.
DATES = re.compile(
    r",?\s*((?:[A-Z][a-z]{2,8}\.?\s+)?(?:19|20)\d{2}\s*(?:-|–|—|to|until)\s*"
    r"(?:(?:[A-Z][a-z]{2,8}\.?\s+)?(?:19|20)\d{2}|[Pp]resent|[Nn]ow|[Cc]urrent|[Tt]oday))\s*$"
)


def split_dates(heading: str) -> tuple[str, str | None]:
    """A role heading without its closing date range, and that range if it has one."""
    match = DATES.search(heading)
    if match is None or match.start() == 0:
        return heading, None
    return heading[: match.start()].rstrip(" ,"), match.group(1)


def _blank_document(name: str | None, title: str) -> DocumentObject:
    document = Document()
    # python-docx would otherwise name itself as the author.
    document.core_properties.author = name or ""
    document.core_properties.title = title
    document.core_properties.comments = ""
    # The template's own dates would otherwise say 2013.
    now = datetime.now(UTC)
    document.core_properties.created = now
    document.core_properties.modified = now
    return document


def _bytes(document: DocumentObject) -> bytes:
    out = BytesIO()
    document.save(out)
    return out.getvalue()


# --- The plain pair ----------------------------------------------------------------------


def _header(document: DocumentObject, name: str | None, contact: str | None) -> None:
    if name:
        document.add_paragraph().add_run(name).bold = True
    if contact:
        document.add_paragraph(contact)


def resume_docx(resume: Resume, name: str | None, contact: str | None) -> bytes:
    document = _blank_document(name, "Resume")
    _header(document, name, contact)
    for section in resume.sections:
        document.add_heading(section.heading, level=2)
        if section.kind == "skills":
            document.add_paragraph(", ".join(skill.text for skill in section.claims))
        else:
            for claim in section.claims:
                document.add_paragraph(claim.text)
        for role in section.roles:
            document.add_paragraph().add_run(role.heading.text).bold = True
            for line in role.lines:
                document.add_paragraph(line.text, style="List Bullet")
    return _bytes(document)


def cover_letter_docx(letter: CoverLetter, name: str | None, contact: str | None) -> bytes:
    document = _blank_document(name, "Cover letter")
    _header(document, name, contact)
    for paragraph in letter.paragraphs:
        document.add_paragraph(" ".join(sentence.text for sentence in paragraph))
    if name:
        document.add_paragraph(name)
    return _bytes(document)


# --- The styled pair ---------------------------------------------------------------------


def _styled_document(name: str | None, title: str) -> DocumentObject:
    document = _blank_document(name, title)
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = DARK
    for page in document.sections:
        page.left_margin = page.right_margin = Inches(0.75)
        page.top_margin = page.bottom_margin = Inches(0.6)
    return document


def _border(paragraph: Paragraph, colour: str, fill: str | None = None) -> None:
    """A thin rule under the paragraph, and a light band behind it when `fill` is given."""
    properties = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("val", "single"), ("sz", "6"), ("space", "1"), ("color", colour)):
        bottom.set(qn(f"w:{key}"), value)
    borders.append(bottom)
    properties.append(borders)
    if fill:
        shading = OxmlElement("w:shd")
        for key, value in (("val", "clear"), ("color", "auto"), ("fill", fill)):
            shading.set(qn(f"w:{key}"), value)
        properties.append(shading)


def _run(
    paragraph: Paragraph, text: str, colour: RGBColor, size: float, bold: bool = False
) -> None:
    run = paragraph.add_run(text)
    run.font.color.rgb = colour
    run.font.size = Pt(size)
    run.bold = bold


def _styled_header(
    document: DocumentObject, name: str | None, contact: str | None, accent: str
) -> None:
    colour = RGBColor.from_string(ACCENTS[accent][0])
    if name:
        line = document.add_paragraph()
        first, _, surname = name.rpartition(" ")
        if first:
            _run(line, f"{first} ", DARK, 24, bold=True)
        _run(line, surname, colour, 24, bold=True)
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER
        line.paragraph_format.space_after = Pt(2)
    if contact:
        line = document.add_paragraph()
        _border(line, ACCENTS[accent][0])
        _run(line, contact, DARK, 10)
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _heading(document: DocumentObject, text: str, accent: str) -> None:
    colour, fill = ACCENTS[accent]
    line = document.add_paragraph()
    _border(line, colour, fill)
    _run(line, text, RGBColor.from_string(colour), 11, bold=True)
    line.runs[0].font.all_caps = True
    line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    line.paragraph_format.space_before = Pt(10)
    line.paragraph_format.space_after = Pt(4)


def _columns(document: DocumentObject, count: int) -> None:
    """Start a run of `count` page columns, which an ATS reads in order, unlike a table."""
    columns = document.add_section(WD_SECTION.CONTINUOUS)._sectPr.find(qn("w:cols"))
    if columns is None:
        columns = OxmlElement("w:cols")
        document.sections[-1]._sectPr.append(columns)
    columns.set(qn("w:num"), str(count))
    columns.set(qn("w:space"), "360")


def styled_resume_docx(resume: Resume, name: str | None, contact: str | None, accent: str) -> bytes:
    document = _styled_document(name, "Resume")
    _styled_header(document, name, contact, accent)
    page = document.sections[0]
    right_margin_tab = page.page_width - page.left_margin - page.right_margin  # type: ignore[operator]
    for section in resume.sections:
        _heading(document, section.heading, accent)
        if section.kind == "skills":
            _columns(document, 2)
            for skill in section.claims:
                document.add_paragraph(skill.text, style="List Bullet")
            _columns(document, 1)
        else:
            for claim in section.claims:
                document.add_paragraph(claim.text)
        for role in section.roles:
            title, dates = split_dates(role.heading.text)
            line = document.add_paragraph()
            line.paragraph_format.tab_stops.add_tab_stop(right_margin_tab, WD_TAB_ALIGNMENT.RIGHT)
            line.paragraph_format.space_before = Pt(6)
            _run(line, title, DARK, 10.5, bold=True)
            if dates:
                _run(line, f"\t{dates}", DARK, 10)
            for bullet in role.lines:
                document.add_paragraph(bullet.text, style="List Bullet")
    return _bytes(document)


def styled_cover_letter_docx(
    letter: CoverLetter, name: str | None, contact: str | None, accent: str
) -> bytes:
    document = _styled_document(name, "Cover letter")
    _styled_header(document, name, contact, accent)
    for paragraph in letter.paragraphs:
        line = document.add_paragraph(" ".join(sentence.text for sentence in paragraph))
        line.paragraph_format.space_after = Pt(8)
    if name:
        document.add_paragraph(name)
    return _bytes(document)


# --- Downloads ---------------------------------------------------------------------------


def filename(name: str | None, role: str, employer: str | None, document: str) -> str:
    """`Name-Role-Employer`, then which document it is, e.g. `Sam-Rivera-...-Resume.docx`."""
    # A pasted posting's title often names the employer already.
    if employer and employer.casefold() in role.casefold():
        employer = None
    parts = (name, role, employer, document)
    safe = [re.sub(r"[^\w]+", "-", part).strip("-_")[:MAX_FILENAME_PART] for part in parts if part]
    return "-".join(part for part in safe if part) + ".docx"


def _file(
    pack: Any, which: Literal["Resume", "Cover letter"], style: Style
) -> tuple[bytes, list[str]]:
    """The file, and the lines an ATS must read back from it in order."""
    name, contact, accent = pack["name"], pack["contact"], pack["accent_colour"]
    signature = [line for line in (name, contact) if line]
    if which == "Resume":
        resume = Resume(**pack["resume"])
        content = (
            styled_resume_docx(resume, name, contact, accent)
            if style == "styled"
            else resume_docx(resume, name, contact)
        )
        return content, [*signature, *(claim.text for claim in resume.all_claims())]
    letter = CoverLetter(**pack["cover_letter"])
    content = (
        styled_cover_letter_docx(letter, name, contact, accent)
        if style == "styled"
        else cover_letter_docx(letter, name, contact)
    )
    return content, [*signature, *(s.text for paragraph in letter.paragraphs for s in paragraph)]


def _download(
    user_id: UUID, application_id: UUID, which: Literal["Resume", "Cover letter"], style: Style
) -> Response:
    with connect() as conn:
        pack = latest_pack(conn, user_id, application_id)
    check_reviewed(pack)
    content, lines = _file(pack, which, style)
    found = ats.problems(content, lines)
    if found:
        raise HTTPException(
            409,
            "This file didn't pass the ATS check, so it can't be downloaded: " + "; ".join(found),
        )
    document = which if style == "styled" else f"{which} plain"
    name = filename(pack["name"], pack["title"], pack["employer"], document)
    return Response(
        content,
        media_type=DOCX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.get("/api/applications/{application_id}/resume.docx")
def download_resume(application_id: UUID, user_id: UserId, style: Style = "styled") -> Response:
    return _download(user_id, application_id, "Resume", style)


@router.get("/api/applications/{application_id}/cover-letter.docx")
def download_cover_letter(
    application_id: UUID, user_id: UserId, style: Style = "styled"
) -> Response:
    return _download(user_id, application_id, "Cover letter", style)
