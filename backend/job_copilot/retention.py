"""Automatic clean-up on the spec's retention schedule, and sending queued trace deletions.

Deletion is permanent, with no hidden copy. Each period below is the spec's retention table;
anything not listed stays until the person deletes it.
"""

import logging
from typing import Any
from uuid import UUID

import httpx

from job_copilot import gateway
from job_copilot.applications import UNOPENED_PACK_DELETES_ON, delete_packs, drop_queued_work
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

# The day each thing is deleted. Clean-up deletes on that day, the day its notice names.
FILTERED_DELETES_ON = f"(p.created_at + interval '{FILTERED_DAYS} days')::date"
EXPIRED_POSTING_DELETES_ON = f"(p.expired_at + interval '{EXPIRED_POSTING_DAYS} days')::date"
OTHER_VERSIONS_DELETES_ON = f"(a.submitted_at + interval '{OTHER_VERSIONS_DAYS} days')::date"
EVAL_RUN_DELETES_ON = f"(r.started_at + interval '{EVAL_RUN_MONTHS} months')::date"
LEDGER_DELETES_ON = f"(created_at + interval '{LEDGER_MONTHS} months')::date"


def _delete_postings(conn: Any, user_id: UUID, deletes_on: str) -> None:
    """Delete the person's postings whose day `deletes_on` (about posting `p`) has come, with
    their Matches.

    A sourced posting's ID is kept, as when the person deletes one, so a search doesn't add it
    back. Postings with an Application are never deleted here: they stay with it.
    """
    postings = conn.execute(
        f"""SELECT id, source, external_id FROM job_postings p
            WHERE p.user_id = %s AND {deletes_on} <= current_date
              AND NOT EXISTS (SELECT 1 FROM applications a
                              WHERE a.job_posting_id = p.id AND a.user_id = p.user_id)""",
        (user_id,),
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
    _delete_postings(conn, user_id, f"p.status = 'filtered' AND {FILTERED_DELETES_ON}")
    _delete_postings(conn, user_id, EXPIRED_POSTING_DELETES_ON)
    unopened = conn.execute(
        f"""SELECT a.id FROM applications a
            WHERE a.user_id = %s AND a.submitted_at IS NULL
              AND {UNOPENED_PACK_DELETES_ON} <= current_date""",
        (user_id,),
    ).fetchall()
    delete_packs(conn, user_id, [a["id"] for a in unopened])
    unsent_versions = conn.execute(
        f"""DELETE FROM application_packs pack USING applications a
            WHERE pack.application_id = a.id AND pack.user_id = a.user_id AND a.user_id = %s
              AND {OTHER_VERSIONS_DELETES_ON} <= current_date
              AND pack.id IS DISTINCT FROM a.submitted_pack_id
            RETURNING pack.id""",
        (user_id,),
    ).fetchall()
    drop_queued_work(conn, user_id, "pack_id", [p["id"] for p in unsent_versions])
    conn.execute(
        f"""DELETE FROM eval_results e USING eval_runs r
            WHERE e.run_id = r.id AND e.user_id = r.user_id AND r.user_id = %s
              AND {EVAL_RUN_DELETES_ON} <= current_date""",
        (user_id,),
    )
    conn.execute(
        f"DELETE FROM eval_runs r WHERE user_id = %s AND {EVAL_RUN_DELETES_ON} <= current_date",
        (user_id,),
    )
    ledger_due = f"user_id = %s AND {LEDGER_DELETES_ON} <= current_date"
    conn.execute(
        f"""INSERT INTO trace_deletions (trace_id)
            SELECT trace_id FROM model_calls WHERE {ledger_due} AND trace_id IS NOT NULL
            ON CONFLICT DO NOTHING""",
        (user_id,),
    )
    conn.execute(f"DELETE FROM model_calls WHERE {ledger_due}", (user_id,))


def clean_up() -> None:
    """Delete everything past its retention period, one person at a time."""
    with connect() as conn:
        users = [row["id"] for row in conn.execute("SELECT id FROM users").fetchall()]
    for user_id in users:
        with connect() as conn:
            _clean_up_user(conn, user_id)
    log.info("Retention clean-up done for %s users", len(users))


def send_trace_deletions() -> None:
    """Delete queued traces at Langfuse, at most 50 tries a day. Without tracing set up, they
    wait; a failed one is tried again another day."""
    settings = gateway.trace_settings()
    if settings is None:
        return
    today = "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
    with connect() as conn:
        # Sent deletions are only kept to count today's tries.
        conn.execute("DELETE FROM trace_deletions WHERE sent_at < now() - interval '2 days'")
        tried_today: Any = conn.execute(
            f"SELECT count(*) AS n FROM trace_deletions WHERE tried_at >= {today}"
        ).fetchone()
        waiting = conn.execute(
            f"""SELECT trace_id FROM trace_deletions
                WHERE sent_at IS NULL AND (tried_at IS NULL OR tried_at < {today})
                ORDER BY queued_at LIMIT %s""",
            (max(0, TRACE_DELETIONS_PER_DAY - tried_today["n"]),),
        ).fetchall()
    for row in waiting:
        response = httpx.delete(
            f"{settings.host.rstrip('/')}/api/public/traces/{row['trace_id']}",
            auth=(settings.public_key, settings.secret_key),
            timeout=TRACE_TIMEOUT_SECONDS,
        )
        # Already gone counts as deleted; anything else stays queued for another day.
        sent = response.status_code in (200, 204, 404)
        if not sent:
            log.warning("Trace deletion failed: HTTP %s", response.status_code)
        with connect() as conn:
            conn.execute(
                """UPDATE trace_deletions
                   SET tried_at = now(), sent_at = CASE WHEN %s THEN now() END
                   WHERE trace_id = %s""",
                (sent, row["trace_id"]),
            )
