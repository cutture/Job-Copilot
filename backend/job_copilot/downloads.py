"""Downloads of a verified Application Pack: either pair, as DOCX or PDF.

Each file is rendered from the saved documents, then must pass its format's ATS check, or it's
refused with the reason. Downloads stay locked until the Pack is reviewed.
"""

import re
from collections.abc import Callable
from typing import Any, Literal, NamedTuple
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from job_copilot import ats, documents, pdf
from job_copilot.applications import CoverLetter, Resume, check_reviewed, latest_pack
from job_copilot.db import UserId, connect

router = APIRouter()

MAX_FILENAME_PART = 60
Pair = Literal["styled", "plain"]
FileFormat = Literal["docx", "pdf"]
Which = Literal["Resume", "Cover letter"]


class Renderers(NamedTuple):
    """How one file format is drawn in each pair, checked and served."""

    resume: Callable[..., bytes]
    styled_resume: Callable[..., bytes]
    letter: Callable[..., bytes]
    styled_letter: Callable[..., bytes]
    problems: Callable[[bytes, list[str]], list[str]]
    media_type: str


FORMATS: dict[FileFormat, Renderers] = {
    "docx": Renderers(
        documents.resume_docx,
        documents.styled_resume_docx,
        documents.cover_letter_docx,
        documents.styled_cover_letter_docx,
        ats.problems,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "pdf": Renderers(
        pdf.resume_pdf,
        pdf.styled_resume_pdf,
        pdf.cover_letter_pdf,
        pdf.styled_cover_letter_pdf,
        ats.pdf_problems,
        "application/pdf",
    ),
}


def filename(
    name: str | None,
    role: str,
    employer: str | None,
    document: str,
    file_format: FileFormat = "docx",
) -> str:
    """`Name-Role-Employer`, then which document it is, e.g. `Sam-Rivera-...-Resume.docx`."""
    # A pasted posting's title often names the employer already.
    if employer and employer.casefold() in role.casefold():
        employer = None
    parts = (name, role, employer, document)
    safe = [re.sub(r"[^\w]+", "-", part).strip("-_")[:MAX_FILENAME_PART] for part in parts if part]
    return "-".join(part for part in safe if part) + f".{file_format}"


def _rendered(
    pack: Any, which: Which, pair: Pair, file_format: FileFormat, photo: bytes | None = None
) -> tuple[bytes, list[str]]:
    """The file, and the lines an ATS must read back from it in order."""
    draw = FORMATS[file_format]
    name, contact, accent = pack["name"], pack["contact"], pack["accent_colour"]
    signature = [line for line in (name, contact) if line]
    styled = pair == "styled"
    if which == "Resume":
        resume = Resume(**pack["resume"])
        content = (
            draw.styled_resume(resume, name, contact, accent, photo)
            if styled
            else draw.resume(resume, name, contact)
        )
        return content, [*signature, *(claim.text for claim in resume.all_claims())]
    letter = CoverLetter(**pack["cover_letter"])
    content = (
        draw.styled_letter(letter, name, contact, accent)
        if styled
        else draw.letter(letter, name, contact)
    )
    return content, [*signature, *(s.text for paragraph in letter.paragraphs for s in paragraph)]


# What to do when a file fails the ATS check.
NEXT_STEP = {
    "styled": "Download the plain pair instead.",
    "plain": "Copy the text from the preview, and report this so the layout can be fixed.",
}


def _download(
    user_id: UUID, application_id: UUID, which: Which, pair: Pair, file_format: FileFormat
) -> Response:
    with connect() as conn:
        pack = latest_pack(conn, user_id, application_id)
        # Only the styled resume carries the photo.
        stored = (
            conn.execute("SELECT photo FROM profiles WHERE user_id = %s", (user_id,)).fetchone()
            if which == "Resume" and pair == "styled"
            else None
        )
    check_reviewed(pack)
    photo = bytes(stored["photo"]) if stored and stored["photo"] else None
    content, lines = _rendered(pack, which, pair, file_format, photo)
    found = FORMATS[file_format].problems(content, lines)
    if found:
        raise HTTPException(
            409,
            f"This file didn't pass the ATS check, so it can't be downloaded: {'; '.join(found)}. "
            + NEXT_STEP[pair],
        )
    document = which if pair == "styled" else f"{which} plain"
    name = filename(pack["name"], pack["title"], pack["employer"], document, file_format)
    return Response(
        content,
        media_type=FORMATS[file_format].media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.get("/api/applications/{application_id}/resume.docx")
def download_resume(application_id: UUID, user_id: UserId, pair: Pair = "styled") -> Response:
    return _download(user_id, application_id, "Resume", pair, "docx")


@router.get("/api/applications/{application_id}/cover-letter.docx")
def download_cover_letter(application_id: UUID, user_id: UserId, pair: Pair = "styled") -> Response:
    return _download(user_id, application_id, "Cover letter", pair, "docx")


@router.get("/api/applications/{application_id}/resume.pdf")
def download_resume_pdf(application_id: UUID, user_id: UserId, pair: Pair = "styled") -> Response:
    return _download(user_id, application_id, "Resume", pair, "pdf")


@router.get("/api/applications/{application_id}/cover-letter.pdf")
def download_cover_letter_pdf(
    application_id: UUID, user_id: UserId, pair: Pair = "styled"
) -> Response:
    return _download(user_id, application_id, "Cover letter", pair, "pdf")
