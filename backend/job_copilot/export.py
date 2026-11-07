"""Export: a person's Profile, Applications and Packs as readable files, in one zip.

It holds only that person's rows. There's no matching import.
"""

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response

from job_copilot.applications import CoverLetter, Resume, application_view
from job_copilot.db import UserId, connect
from job_copilot.profile import get_profile

router = APIRouter()

README = """Your Job Copilot data, exported {when}.

profile.json        Your Profile: facts, preferences, your resume's text and your Evidence.
photo.jpg           The photo on your styled resume, if there is one.
applications/       One folder for each Application:
  application.json  The Application, its posting and the rating you saw.
  pack-vN.json      Each Application Pack version, with its Removed Claims.
  resume-vN.md      That version's resume, as text.
  cover-letter-vN.md  That version's cover letter, as text.

Files you downloaded before are on your computer, not here. Job Copilot can't import this file.
"""


def _slug(text: str) -> str:
    """Only letters, digits and dashes, so a posting's title can't name a path."""
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:40] or "Application"


def _resume_text(resume: Resume, name: str | None, contact: str | None) -> str:
    lines = [f"# {name}" if name else "", contact or ""]
    for section in resume.sections:
        lines += ["", f"## {section.heading}"]
        if section.kind == "summary":
            lines.append(" ".join(sentence.text for sentence in section.claims))
            continue
        lines += [f"- {claim.text}" for claim in section.claims]
        lines += [
            f"- **{group.heading.text}:** {', '.join(skill.text for skill in group.claims)}"
            for group in section.groups
        ]
        for role in section.roles:
            lines += ["", f"### {role.heading.text}", *(f"- {line.text}" for line in role.lines)]
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def _cover_letter_text(letter: CoverLetter, name: str | None) -> str:
    paragraphs = [" ".join(sentence.text for sentence in p) for p in letter.paragraphs]
    return "\n\n".join([*paragraphs, *([name] if name else [])]) + "\n"


def _write_json(archive: zipfile.ZipFile, path: str, value: Any) -> None:
    archive.writestr(path, json.dumps(value, indent=2, ensure_ascii=False, default=str))


@router.get("/api/export")
def export(user_id: UserId) -> Response:
    """Download everything the person keeps in Job Copilot, as readable files."""
    profile = get_profile(user_id)
    with connect() as conn:
        photo = conn.execute(
            "SELECT photo FROM profiles WHERE user_id = %s AND photo IS NOT NULL", (user_id,)
        ).fetchone()
        applications = conn.execute(
            """SELECT a.id, p.text AS posting, a.requirements
               FROM applications a
               JOIN job_postings p ON p.id = a.job_posting_id AND p.user_id = a.user_id
               WHERE a.user_id = %s ORDER BY a.created_at""",
            (user_id,),
        ).fetchall()
        packs = conn.execute(
            """SELECT application_id, version, status, model, resume, cover_letter,
                      removed_claims, created_at
               FROM application_packs WHERE user_id = %s ORDER BY version""",
            (user_id,),
        ).fetchall()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", README.format(when=datetime.now(UTC).date().isoformat()))
        _write_json(archive, "profile.json", profile.model_dump(mode="json"))
        if photo:
            archive.writestr("photo.jpg", bytes(photo["photo"]))
        for number, row in enumerate(applications, start=1):
            _write_application(archive, user_id, number, row, packs, profile.name, profile.contact)
    return Response(
        out.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="job-copilot-export.zip"'},
    )


def _write_application(
    archive: zipfile.ZipFile,
    user_id: UUID,
    number: int,
    row: Any,
    packs: list[Any],
    name: str | None,
    contact: str | None,
) -> None:
    view = application_view(user_id, row["id"])
    folder = f"applications/{number:02d}-{_slug(view.title)}"
    _write_json(
        archive,
        f"{folder}/application.json",
        {
            **view.model_dump(mode="json", exclude={"pack"}),
            "posting": row["posting"],
            "requirements": row["requirements"],
        },
    )
    for pack in (p for p in packs if p["application_id"] == row["id"]):
        version = pack["version"]
        _write_json(archive, f"{folder}/pack-v{version}.json", dict(pack))
        if pack["status"] == "ready":
            archive.writestr(
                f"{folder}/resume-v{version}.md",
                _resume_text(Resume(**pack["resume"]), name, contact),
            )
            archive.writestr(
                f"{folder}/cover-letter-v{version}.md",
                _cover_letter_text(CoverLetter(**pack["cover_letter"]), name),
            )
