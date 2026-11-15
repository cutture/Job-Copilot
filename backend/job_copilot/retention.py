"""Automatic clean-up on the spec's retention schedule, and sending queued trace deletions.

Deletion is permanent, with no hidden copy. Each period below is the spec's retention table;
anything not listed stays until the person deletes it.
"""

import logging
from typing import Any
from uuid import UUID

import httpx

from job_copilot import gateway
from job_copilot.applications import (
    LATEST_PACK,
    UNOPENED_PACK_DAYS,
    delete_packs,
    drop_queued_work,
)
from job_copilot.db import connect

log = logging.getLogger(__name__)

FILTERED_DAYS = 30
EXPIRED_POSTING_DAYS = 90
# Pack versions other than the one sent, once an Application is Submitted.
OTHER_VERSIONS_DAYS = 30
EVAL_RUN_MONTHS = 12
LEDGER_MONTHS = 13
# Langfuse allows 50 trace deletions a day.
TRACE_DELETIONS_PER_DAY = 50
TRACE_TIMEOUT_SECONDS = 10

# When a Filtered Posting goes, for the notice before it does.
FILTERED_DELETES_ON = f"(p.created_at + interval '{FILTERED_DAYS} days')::date"


def _delete_postings(conn: Any, user_id: UUID, where: str, days: int) -> None:
    """Delete the person's postings matching `where` (about posting `p`) with their Matches.

    A sourced posting's ID is kept, as when the person deletes one, so a search doesn't add it
    back. Postings with an Application are never matched: they stay with it.
    """
    postings = conn.execute(
        f"""SELECT id, source, external_id FROM job_postings p
            WHERE p.user_id = %s AND {where}
              AND NOT EXISTS (SELECT 1 FROM applications a
                              WHERE a.job_posting_id = p.id AND a.user_id = p.user_id)""",
        (user_id, days),
    ).fetchall()
    ids = [p["id"] for p in postings]
    drop_queued_work(conn, user_id, "job_posting_id", ids)
    conn.execute(
        "DELETE FROM matches WHERE user_id = %s AND job_posting_id = ANY(%s)", (user_id, ids)
    )
    for posting in postings:
        if posting["external_id"]:
            conn.execute(
                """INSERT INTO deleted_postings (user_id, source, external_id)
                   VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                (user_id, posting["source"], posting["external_id"]),
            )
    conn.execute("DELETE FROM job_postings WHERE user_id = %s AND id = ANY(%s)", (user_id, ids))


def _clean_up_user(conn: Any, user_id: UUID) -> None:
    _delete_postings(
        conn,
        user_id,
        "p.status = 'filtered' AND p.created_at < now() - %s * interval '1 day'",
        FILTERED_DAYS,
    )
    _delete_postings(
        conn, user_id, "p.expired_at < now() - %s * interval '1 day'", EXPIRED_POSTING_DAYS
    )
    unopened = conn.execute(
        """SELECT a.id FROM applications a
           WHERE a.user_id = %s AND a.submitted_at IS NULL
             AND a.opened_at < now() - %s * interval '1 day'""",
        (user_id, UNOPENED_PACK_DAYS),
    ).fetchall()
    delete_packs(conn, user_id, [a["id"] for a in unopened])
    others = conn.execute(
        f"""DELETE FROM application_packs pack USING applications a
            WHERE pack.application_id = a.id AND pack.user_id = a.user_id AND a.user_id = %s
              AND a.submitted_at < now() - %s * interval '1 day'
              AND pack.id <> {LATEST_PACK}
            RETURNING pack.id""",
        (user_id, OTHER_VERSIONS_DAYS),
    ).fetchall()
    drop_queued_work(conn, user_id, "pack_id", [p["id"] for p in others])
    conn.execute(
        """DELETE FROM eval_results e USING eval_runs r
           WHERE e.run_id = r.id AND e.user_id = r.user_id AND r.user_id = %s
             AND r.started_at < now() - %s * interval '1 month'""",
        (user_id, EVAL_RUN_MONTHS),
    )
    conn.execute(
        "DELETE FROM eval_runs WHERE user_id = %s AND started_at < now() - %s * interval '1 month'",
        (user_id, EVAL_RUN_MONTHS),
    )
    old_ledger = "user_id = %s AND created_at < now() - %s * interval '1 month'"
    conn.execute(
        f"""INSERT INTO trace_deletions (trace_id)
            SELECT trace_id FROM model_calls WHERE {old_ledger} AND trace_id IS NOT NULL
            ON CONFLICT DO NOTHING""",
        (user_id, LEDGER_MONTHS),
    )
    conn.execute(f"DELETE FROM model_calls WHERE {old_ledger}", (user_id, LEDGER_MONTHS))


def clean_up() -> None:
    """Delete everything past its retention period, one person at a time."""
    with connect() as conn:
        users = [row["id"] for row in conn.execute("SELECT id FROM users").fetchall()]
    for user_id in users:
        with connect() as conn:
            _clean_up_user(conn, user_id)
    log.info("Retention clean-up done for %s users", len(users))


def send_trace_deletions() -> None:
    """Delete queued traces at Langfuse, at most 50 a day. Without tracing set up, they wait."""
    settings = gateway.trace_settings()
    if settings is None:
        return
    with connect() as conn:
        # Sent deletions are only kept to count today's.
        conn.execute("DELETE FROM trace_deletions WHERE sent_at < now() - interval '2 days'")
        sent_today: Any = conn.execute(
            """SELECT count(*) AS n FROM trace_deletions
               WHERE sent_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"""
        ).fetchone()
        waiting = conn.execute(
            """SELECT trace_id FROM trace_deletions WHERE sent_at IS NULL
               ORDER BY queued_at LIMIT %s""",
            (max(0, TRACE_DELETIONS_PER_DAY - sent_today["n"]),),
        ).fetchall()
    for row in waiting:
        response = httpx.delete(
            f"{settings.host.rstrip('/')}/api/public/traces/{row['trace_id']}",
            auth=(settings.public_key, settings.secret_key),
            timeout=TRACE_TIMEOUT_SECONDS,
        )
        # Already gone counts as deleted; anything else stays queued for another day.
        if response.status_code not in (200, 204, 404):
            log.warning("Trace deletion failed: HTTP %s", response.status_code)
            continue
        with connect() as conn:
            conn.execute(
                "UPDATE trace_deletions SET sent_at = now() WHERE trace_id = %s", (row["trace_id"],)
            )
