"""Deleting a person's records: one item at a time, or everything at once.

Deletion is permanent, with no hidden copy. Two things are kept on purpose, and neither holds
personal data: a deleted Source posting's ID, so a search doesn't add it back, and trace IDs
waiting to be deleted at the tracing service, kept without any user.
"""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from job_copilot.applications import (
    NEXT_STEP,
    ApplicationView,
    Claim,
    CoverLetter,
    RemovedClaim,
    Resume,
    Role,
    application_view,
    latest_pack,
    queue_pack,
)
from job_copilot.db import UserId, connect

router = APIRouter()

# Every table holding a person's rows, in an order that deletes children first. A new table
# with a user_id column must join this list; a test checks it against the database.
USER_TABLES = (
    "jobs",
    "application_packs",
    "applications",
    "matches",
    "deleted_postings",
    "job_postings",
    "watchlist",
    "searches",
    "model_calls",
    "evidence",
    "profiles",
)
# What each table is called in the report.
LABELS = {
    "jobs": "Queued work",
    "application_packs": "Application Pack versions",
    "applications": "Applications",
    "matches": "Match ratings",
    "deleted_postings": "Deleted posting IDs",
    "job_postings": "Job Postings",
    "watchlist": "Watchlist employers",
    "searches": "Searches",
    "model_calls": "Spending ledger entries",
    "evidence": "Evidence items",
    "profiles": "Profile",
}
EVIDENCE_DELETED = "Its Evidence was deleted from your Profile."
# Said in every report, because no app can delete these.
NOT_DELETED = [
    "Files you downloaded stay on your computer. Delete them yourself.",
    "Model providers keep what they received under their own policies. Anthropic says it keeps "
    "API data for 30 days, or up to 2 years if a request is flagged.",
    "API keys in your .env file aren't stored by Job Copilot. Remove them yourself.",
    "Job Copilot makes no backups in local mode. Backups you made yourself aren't touched.",
]


class DeleteEverything(BaseModel):
    confirm: Literal["DELETE"]


class DeletionReport(BaseModel):
    deleted: dict[str, int]
    not_deleted: list[str]


def _drop_queued(conn: Any, user_id: UUID, key: str, ids: list[Any]) -> None:
    """Queued work for records that are going, so a worker never writes them back."""
    conn.execute(
        "DELETE FROM jobs WHERE user_id = %s AND payload ->> %s = ANY(%s)",
        (user_id, key, [str(i) for i in ids]),
    )


def _delete_packs(conn: Any, user_id: UUID, where: str, values: tuple[Any, ...]) -> None:
    packs = conn.execute(
        f"DELETE FROM application_packs WHERE user_id = %s AND {where} RETURNING id",
        (user_id, *values),
    ).fetchall()
    _drop_queued(conn, user_id, "pack_id", [p["id"] for p in packs])


def _delete_applications(conn: Any, user_id: UUID, where: str, values: tuple[Any, ...]) -> int:
    """Delete Applications and their Packs. Their spending ledger entries stay, unlinked."""
    ids = [
        row["id"]
        for row in conn.execute(
            f"SELECT id FROM applications WHERE user_id = %s AND {where}", (user_id, *values)
        ).fetchall()
    ]
    _delete_packs(conn, user_id, "application_id = ANY(%s)", (ids,))
    conn.execute("DELETE FROM applications WHERE user_id = %s AND id = ANY(%s)", (user_id, ids))
    return len(ids)


@router.delete("/api/job-postings/{posting_id}", status_code=204)
def delete_posting(posting_id: UUID, user_id: UserId) -> None:
    """Delete a Job Posting with its Match, and its Application and Pack if it has one."""
    with connect() as conn:
        posting: Any = conn.execute(
            "SELECT source, external_id FROM job_postings WHERE id = %s AND user_id = %s",
            (posting_id, user_id),
        ).fetchone()
        if posting is None:
            raise HTTPException(404, "Job Posting not found")
        _delete_applications(conn, user_id, "job_posting_id = %s", (posting_id,))
        _drop_queued(conn, user_id, "job_posting_id", [posting_id])
        conn.execute(
            "DELETE FROM matches WHERE job_posting_id = %s AND user_id = %s", (posting_id, user_id)
        )
        if posting["external_id"]:
            conn.execute(
                """INSERT INTO deleted_postings (user_id, source, external_id)
                   VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                (user_id, posting["source"], posting["external_id"]),
            )
        conn.execute(
            "DELETE FROM job_postings WHERE id = %s AND user_id = %s", (posting_id, user_id)
        )


@router.delete("/api/applications/{application_id}", status_code=204)
def delete_application(application_id: UUID, user_id: UserId) -> None:
    """Delete an Application and its Pack. The Job Posting and its Match stay."""
    with connect() as conn:
        if not _delete_applications(conn, user_id, "id = %s", (application_id,)):
            raise HTTPException(404, "Application not found")


@router.delete("/api/applications/{application_id}/pack")
def delete_pack(application_id: UUID, user_id: UserId) -> ApplicationView:
    """Delete the newest Pack version; the Application stays."""
    with connect() as conn:
        pack = latest_pack(conn, user_id, application_id)
        if pack["id"] is None:
            raise HTTPException(409, "This Application has no Application Pack.")
        _delete_packs(conn, user_id, "id = %s", (pack["id"],))
    return application_view(user_id, application_id)


@router.post("/api/applications/{application_id}/pack", status_code=202)
def write_new_pack(application_id: UUID, user_id: UserId) -> ApplicationView:
    """Write a new Pack for an Application whose Pack was deleted."""
    with connect() as conn:
        if latest_pack(conn, user_id, application_id)["id"] is not None:
            raise HTTPException(409, "This Application already has an Application Pack.")
        pack: Any = conn.execute(
            """INSERT INTO application_packs (user_id, application_id, version)
               SELECT %s, %s, COALESCE(max(version), 0) + 1 FROM application_packs
               WHERE application_id = %s RETURNING id""",
            (user_id, application_id, application_id),
        ).fetchone()
        queue_pack(conn, user_id, pack["id"])
    return application_view(user_id, application_id)


def _without(
    resume: Resume, letter: CoverLetter, text: str, submitted: bool
) -> tuple[bool, list[RemovedClaim]]:
    """Take deleted Evidence out of a Pack's Claims, in place.

    A Submitted Pack keeps every Claim as it was sent, with that Evidence marked "source
    removed". Otherwise a Claim that loses its only Evidence becomes a Removed Claim.
    """
    changed = False
    removed: list[RemovedClaim] = []

    def still_supported(claim: Claim) -> bool:
        nonlocal changed
        gone = [ref for ref in claim.evidence if ref.text == text]
        if not gone:
            return True
        changed = True
        if submitted:
            for ref in gone:
                ref.source_removed = True
            return True
        claim.evidence = [ref for ref in claim.evidence if ref.text != text]
        if claim.evidence:
            return True
        removed.append(
            RemovedClaim(
                text=claim.text,
                kind="evidence_deleted",
                reason=EVIDENCE_DELETED,
                next_step=NEXT_STEP,
            )
        )
        return False

    def kept(claims: list[Claim]) -> list[Claim]:
        return [c for c in claims if still_supported(c)]

    roles: list[Role] = []
    for role in resume.experience:
        if still_supported(role.heading):
            roles.append(Role(heading=role.heading, lines=kept(role.lines)))
        else:
            removed.extend(
                RemovedClaim(
                    text=line.text,
                    kind="with_heading",
                    reason="Its job heading was taken out.",
                    next_step=NEXT_STEP,
                )
                for line in role.lines
            )
    resume.skills, resume.experience = kept(resume.skills), roles
    resume.education = kept(resume.education)
    letter.paragraphs = [p for p in map(kept, letter.paragraphs) if p]
    return changed, removed


def evidence_deleted(conn: Any, user_id: UUID, text: str) -> None:
    """What deleting an Evidence item changes in Matches and Packs."""
    # ponytail: Matches and Packs keep Evidence text, not IDs, so two items with the same text
    # count as one; store Evidence IDs with them if that ever matters.
    conn.execute(
        """UPDATE matches m SET profile_changed = true
           WHERE m.user_id = %s
             AND NOT EXISTS (SELECT 1 FROM applications a
                             WHERE a.job_posting_id = m.job_posting_id AND a.user_id = m.user_id)
             AND EXISTS (SELECT 1 FROM jsonb_array_elements(m.requirements) r,
                                       jsonb_array_elements_text(r -> 'evidence') cited
                         WHERE cited = %s)""",
        (user_id, text),
    )
    packs = conn.execute(
        """SELECT pack.id, pack.resume, pack.cover_letter, pack.removed_claims,
                  a.submitted_at IS NOT NULL AS submitted
           FROM application_packs pack
           JOIN applications a ON a.id = pack.application_id AND a.user_id = pack.user_id
           WHERE pack.user_id = %s AND pack.status = 'ready'
           FOR UPDATE OF pack""",
        (user_id,),
    ).fetchall()
    for pack in packs:
        resume, letter = Resume(**pack["resume"]), CoverLetter(**pack["cover_letter"])
        changed, removed = _without(resume, letter, text, pack["submitted"])
        if not changed:
            continue
        conn.execute(
            # Changed documents need reviewing again; a Submitted Pack's review stays.
            """UPDATE application_packs SET resume = %s, cover_letter = %s,
                   removed_claims = removed_claims || %s,
                   reviewed_at = CASE WHEN %s THEN reviewed_at END
               WHERE id = %s AND user_id = %s""",
            (
                Jsonb(resume.model_dump()),
                Jsonb(letter.model_dump()),
                Jsonb([r.model_dump() for r in removed]),
                pack["submitted"],
                pack["id"],
                user_id,
            ),
        )


@router.delete("/api/evidence/{evidence_id}", status_code=204)
def delete_evidence(evidence_id: int, user_id: UserId) -> None:
    with connect() as conn:
        deleted: Any = conn.execute(
            "DELETE FROM evidence WHERE id = %s AND user_id = %s RETURNING text",
            (evidence_id, user_id),
        ).fetchone()
        if deleted is None:
            raise HTTPException(404, "Evidence not found")
        evidence_deleted(conn, user_id, deleted["text"])


@router.post("/api/delete-everything")
def delete_everything(_: DeleteEverything, user_id: UserId) -> DeletionReport:
    """Delete every record of the person's. The typed DELETE is checked by the request model."""
    with connect() as conn:
        traces: Any = conn.execute(
            """INSERT INTO trace_deletions (trace_id)
               SELECT trace_id FROM model_calls WHERE user_id = %s AND trace_id IS NOT NULL
               ON CONFLICT DO NOTHING RETURNING trace_id""",
            (user_id,),
        ).fetchall()
        deleted = {
            LABELS[table]: conn.execute(
                f"DELETE FROM {table} WHERE user_id = %s", (user_id,)
            ).rowcount
            for table in USER_TABLES
        }
    not_deleted = list(NOT_DELETED)
    if traces:
        # ponytail: the IDs wait in trace_deletions until the trace deletion job sends them, at
        # most 50 a day under Langfuse's limit.
        not_deleted.insert(
            0,
            f"{len(traces)} traces at Langfuse are queued for deletion, up to 50 a day. They hold "
            "masked records of each model call, never your resume text.",
        )
    return DeletionReport(deleted=deleted, not_deleted=not_deleted)
