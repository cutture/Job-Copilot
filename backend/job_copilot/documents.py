"""The document renderer: DOCX files of a verified Application Pack.

It takes only the saved documents, which hold verified Claims and no Removed Claims, and writes
only their text: no Evidence, labels, tables or images. The resume is one column, its sections
in the order the Pack holds them.
"""

import re
from datetime import UTC, datetime
from io import BytesIO
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from docx import Document
from docx.document import Document as DocumentObject
from fastapi import APIRouter, Response

from job_copilot.applications import CoverLetter, Resume, check_reviewed, latest_pack
from job_copilot.db import UserId, connect

router = APIRouter()

MAX_FILENAME_PART = 60
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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


def _header(document: DocumentObject, name: str | None, contact: str | None) -> None:
    if name:
        document.add_paragraph().add_run(name).bold = True
    if contact:
        document.add_paragraph(contact)


def _bytes(document: DocumentObject) -> bytes:
    out = BytesIO()
    document.save(out)
    return out.getvalue()


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


def filename(name: str | None, role: str, employer: str | None, document: str) -> str:
    """`Name-Role-Employer`, then which document it is, e.g. `Sam-Rivera-...-Resume.docx`."""
    # A pasted posting's title often names the employer already.
    if employer and employer.casefold() in role.casefold():
        employer = None
    parts = (name, role, employer, document)
    safe = [re.sub(r"[^\w]+", "-", part).strip("-_")[:MAX_FILENAME_PART] for part in parts if part]
    return "-".join(part for part in safe if part) + ".docx"


def _download(
    user_id: UUID, application_id: UUID, which: Literal["Resume", "Cover letter"]
) -> Response:
    with connect() as conn:
        pack = latest_pack(conn, user_id, application_id)
    check_reviewed(pack)
    if which == "Resume":
        content = resume_docx(Resume(**pack["resume"]), pack["name"], pack["contact"])
    else:
        content = cover_letter_docx(
            CoverLetter(**pack["cover_letter"]), pack["name"], pack["contact"]
        )
    name = filename(pack["name"], pack["title"], pack["employer"], which)
    return Response(
        content,
        media_type=DOCX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.get("/api/applications/{application_id}/resume.docx")
def download_resume(application_id: UUID, user_id: UserId) -> Response:
    return _download(user_id, application_id, "Resume")


@router.get("/api/applications/{application_id}/cover-letter.docx")
def download_cover_letter(application_id: UUID, user_id: UserId) -> Response:
    return _download(user_id, application_id, "Cover letter")
