"""Deleting a person's records: one item at a time, or everything at once.

Deletion is permanent, with no hidden copy. Two things are kept on purpose, and neither holds
personal data: a deleted Source posting's ID, so a search doesn't add it back, and trace IDs
waiting to be deleted at the tracing service, kept without any user.
"""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from job_copilot.applications import delete_packs, drop_queued_work, forget_evidence
from job_copilot.db import UserId, connect

router = APIRouter()

# Every table holding a person's rows, with its name in the report, in an order that deletes
# children first. A new table with a user_id column must join it; a test checks the database.
USER_TABLES = {
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
# Eval Runs hold only invented data, so they stay unless the person asks for them to go.
EVAL_TABLES = {"eval_results": "Eval Case results", "eval_runs": "Eval Runs"}
# Said in every report, because no app can delete these.
NOT_DELETED = [
    "Files you downloaded stay on your computer. Delete them yourself.",
    "Model providers keep what they received under their own policies. Anthropic says it keeps "
    "API data for 30 days, or up to 2 years if a request is flagged.",
    "API keys in your .env file aren't stored by Job Copilot. Remove them yourself.",
    "Job Copilot makes no backups in local mode. Backups you made yourself aren't touched.",
]
LEDGER_NOTE = (
    "The spending ledger is deleted too, so this month's spending cap starts again from $0."
)


class DeleteEverything(BaseModel):
    confirm: Literal["DELETE"]
    include_eval_runs: bool = False


class DeletionReport(BaseModel):
    deleted: dict[str, int]
    not_deleted: list[str]
    notes: list[str]


def _delete_applications(conn: Any, user_id: UUID, application_ids: list[Any]) -> None:
    """Delete Applications and their Packs. Their spending ledger entries stay, unlinked."""
    delete_packs(conn, user_id, application_ids)
    conn.execute(
        "DELETE FROM applications WHERE user_id = %s AND id = ANY(%s)",
        (user_id, application_ids),
    )


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
        applications = conn.execute(
            "SELECT id FROM applications WHERE job_posting_id = %s AND user_id = %s",
            (posting_id, user_id),
        ).fetchall()
        _delete_applications(conn, user_id, [a["id"] for a in applications])
        drop_queued_work(conn, user_id, "job_posting_id", [posting_id])
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
        found = conn.execute(
            "SELECT 1 FROM applications WHERE id = %s AND user_id = %s FOR UPDATE",
            (application_id, user_id),
        ).fetchone()
        if found is None:
            raise HTTPException(404, "Application not found")
        _delete_applications(conn, user_id, [application_id])


@router.delete("/api/evidence/{evidence_id}", status_code=204)
def delete_evidence(evidence_id: int, user_id: UserId) -> None:
    with connect() as conn:
        deleted: Any = conn.execute(
            "DELETE FROM evidence WHERE id = %s AND user_id = %s RETURNING text",
            (evidence_id, user_id),
        ).fetchone()
        if deleted is None:
            raise HTTPException(404, "Evidence not found")
        forget_evidence(conn, user_id, evidence_id, deleted["text"])


@router.post("/api/delete-everything")
def delete_everything(request: DeleteEverything, user_id: UserId) -> DeletionReport:
    """Delete every record of the person's. The typed DELETE is checked by the request model."""
    with connect() as conn:
        traces: Any = conn.execute(
            """SELECT count(DISTINCT trace_id) AS traces FROM model_calls
               WHERE user_id = %s AND trace_id IS NOT NULL""",
            (user_id,),
        ).fetchone()
        conn.execute(
            """INSERT INTO trace_deletions (trace_id)
               SELECT trace_id FROM model_calls WHERE user_id = %s AND trace_id IS NOT NULL
               ON CONFLICT DO NOTHING""",
            (user_id,),
        )
        tables = USER_TABLES | (EVAL_TABLES if request.include_eval_runs else {})
        deleted = {
            label: conn.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,)).rowcount
            for table, label in tables.items()
        }
    not_deleted = list(NOT_DELETED)
    if traces["traces"]:
        # ponytail: the IDs wait in trace_deletions until the trace deletion job sends them, at
        # most 50 a day under Langfuse's limit.
        not_deleted.insert(
            0,
            f"{traces['traces']} traces at Langfuse are queued for deletion, up to 50 a day. "
            "They hold masked records of each model call, never your resume text.",
        )
    return DeletionReport(deleted=deleted, not_deleted=not_deleted, notes=[LEDGER_NOTE])
