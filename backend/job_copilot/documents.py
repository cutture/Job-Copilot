"""The document renderer: DOCX files of a verified Application Pack.

It takes only the saved documents, which hold verified Claims and no Removed Claims, and writes
only their text: no Evidence, labels, tables or images. The resume is one column ordered Skills,
Experience, Education.
"""

import re
from io import BytesIO
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from docx import Document
from docx.document import Document as DocumentObject
from fastapi import APIRouter, HTTPException, Response

from job_copilot.applications import NOT_REVIEWED, CoverLetter, Resume, latest_pack
from job_copilot.db import UserId, connect

router = APIRouter()

MAX_FILENAME_PART = 60
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _new(name: str | None, title: str) -> DocumentObject:
    document = Document()
    # python-docx would otherwise name itself as the author.
    document.core_properties.author = name or ""
    document.core_properties.title = title
    document.core_properties.comments = ""
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
    document = _new(name, "Resume")
    _header(document, name, contact)
    if resume.skills:
        document.add_heading("Skills", level=2)
        document.add_paragraph(", ".join(skill.text for skill in resume.skills))
    if resume.experience:
        document.add_heading("Experience", level=2)
        for role in resume.experience:
            document.add_paragraph().add_run(role.heading.text).bold = True
            for line in role.lines:
                document.add_paragraph(line.text, style="List Bullet")
    if resume.education:
        document.add_heading("Education", level=2)
        for item in resume.education:
            document.add_paragraph(item.text)
    return _bytes(document)


def cover_letter_docx(letter: CoverLetter, name: str | None, contact: str | None) -> bytes:
    document = _new(name, "Cover letter")
    _header(document, name, contact)
    for paragraph in letter.paragraphs:
        document.add_paragraph(" ".join(sentence.text for sentence in paragraph))
    if name:
        document.add_paragraph(name)
    return _bytes(document)


def filename(name: str | None, role: str, employer: str | None, document: str) -> str:
    """`Name-Role-Employer`, then which document it is, e.g. `Sam-Rivera-...-Resume.docx`."""
    parts = (name, role, employer, document)
    safe = [re.sub(r"[^\w]+", "-", part).strip("-_")[:MAX_FILENAME_PART] for part in parts if part]
    return "-".join(part for part in safe if part) + ".docx"


def _download(
    user_id: UUID, application_id: UUID, which: Literal["Resume", "Cover letter"]
) -> Response:
    with connect() as conn:
        pack = latest_pack(conn, user_id, application_id)
        row: Any = conn.execute(
            """SELECT p.title, p.employer, pr.name, pr.contact
               FROM applications a
               JOIN job_postings p ON p.id = a.job_posting_id AND p.user_id = a.user_id
               LEFT JOIN profiles pr ON pr.user_id = a.user_id
               WHERE a.id = %s AND a.user_id = %s""",
            (application_id, user_id),
        ).fetchone()
    # Downloads stay locked until the person has reviewed this verified Pack.
    if pack["status"] != "ready" or pack["reviewed_at"] is None:
        raise HTTPException(409, NOT_REVIEWED)
    if which == "Resume":
        content = resume_docx(Resume(**pack["resume"]), row["name"], row["contact"])
    else:
        content = cover_letter_docx(
            CoverLetter(**pack["cover_letter"]), row["name"], row["contact"]
        )
    name = filename(row["name"], row["title"], row["employer"], which)
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
