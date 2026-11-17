import json
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from job_copilot import (
    applications,
    eval_runs,
    filter,
    gateway,
    profile,
    rating,
    retention,
    search,
)
from job_copilot.db import connect, current_user_id

log = logging.getLogger(__name__)

IDLE_SECONDS = 2.0
# The hour, in UTC, after which each day's Eval Run is queued.
EVAL_HOUR_UTC = int(os.environ.get("EVAL_HOUR_UTC", "6"))
MAX_TITLE_LENGTH = 120


def _clean_title(answer: str) -> str | None:
    """Model output is untrusted: keep one short line with no control characters."""
    for line in answer.splitlines():
        title = profile.strip_controls(line)
        if title:
            return title[:MAX_TITLE_LENGTH]
    return None


def _process_posting(user_id: UUID, posting_id: str) -> None:
    with connect() as conn:
        posting = conn.execute(
            "SELECT text FROM job_postings WHERE id = %s AND user_id = %s", (posting_id, user_id)
        ).fetchone()
    if posting is None:
        return
    if not filter.is_english(posting["text"]):
        _save(user_id, posting_id, status="filtered", reason="Not written in English")
        return
    facts = filter.read_facts(user_id, posting["text"])
    title = _clean_title(facts.title)
    if title is None:
        raise ValueError("The model returned no title")
    decision = filter.decide(facts, filter.preferences_for(user_id))
    _save(
        user_id,
        posting_id,
        status="received" if decision.passed else "filtered",
        reason=decision.reason,
        title=title,
        posting_type=facts.posting_type,
        salary_note=decision.salary_note,
    )
    if decision.passed:
        rating.queue_ratings(user_id)


def _save(
    user_id: UUID,
    posting_id: str,
    *,
    status: str,
    reason: str | None,
    title: str | None = None,
    posting_type: str | None = None,
    salary_note: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            # A Source gives its own title; only pasted postings need the model's.
            """UPDATE job_postings SET status = %s, filter_reason = %s,
                   title = CASE WHEN external_id IS NULL THEN COALESCE(%s, title) ELSE title END,
                   posting_type = %s, salary_note = %s
               WHERE id = %s AND user_id = %s""",
            (status, reason, title, posting_type, salary_note, posting_id, user_id),
        )


def _mark_unavailable(user_id: UUID, posting_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE job_postings SET status = 'model_unavailable' WHERE id = %s AND user_id = %s",
            (posting_id, user_id),
        )


def _process_posting_job(user_id: UUID, payload: dict[str, Any]) -> None:
    _process_posting(user_id, payload["job_posting_id"])


def _posting_failed(user_id: UUID, payload: dict[str, Any]) -> None:
    _mark_unavailable(user_id, payload["job_posting_id"])


Handler = Callable[[UUID, dict[str, Any]], None]


def _run_eval_case(user_id: UUID, payload: dict[str, Any]) -> None:
    # Imported here, so only the worker loads DeepEval, and only when evals run.
    from job_copilot import evals

    evals.run_queued_case(user_id, payload["run_id"], payload["case_id"])


def _eval_case_failed(user_id: UUID, payload: dict[str, Any]) -> None:
    eval_runs.case_not_recorded(user_id, payload["run_id"], payload["case_id"])


def schedule_daily_evals(now: datetime) -> None:
    """Queue today's Eval Run for the owner, once, after EVAL_HOUR_UTC."""
    if now.hour >= EVAL_HOUR_UTC:
        eval_runs.queue_daily_run(current_user_id(), now)
        eval_runs.queue_challenger_runs(current_user_id(), now)


# The day clean-up last ran, so it runs once a day while the app is running.
# ponytail: kept in memory, so a restart cleans up again that day; harmless, as it's idempotent.
_cleaned_on: date | None = None


def daily_clean_up(now: datetime) -> None:
    """Delete what's past its retention period, and send queued trace deletions, once a day."""
    global _cleaned_on
    if _cleaned_on == now.date():
        return
    _cleaned_on = now.date()
    try:
        retention.clean_up()
        retention.send_trace_deletions()
    except Exception as error:  # Clean-up never stops the worker; it tries again tomorrow.
        log.warning("Retention clean-up failed: %s", type(error).__name__)


def finish_interrupted_evals() -> None:
    """Finish runs a crash left open, so what they recorded shows and counts."""
    eval_runs.finish_interrupted_runs(current_user_id())


# Each kind of job, and what to record if it fails, so one failure never blocks the queue.
HANDLERS: dict[str, tuple[Handler, Handler]] = {
    "process_posting": (_process_posting_job, _posting_failed),
    "extract_evidence": (profile.extract_evidence, profile.mark_extraction_failed),
    "rate_match": (rating.rate_match, rating.mark_not_rated),
    "rescore_match": (rating.rescore_match, rating.rescore_failed),
    "search": (search.run_search, search.finish_search),
    "generate_pack": (applications.generate_pack, applications.pack_failed),
    eval_runs.EVAL_CASE_JOB: (_run_eval_case, _eval_case_failed),
}


def _run(job: dict[str, Any]) -> None:
    handlers = HANDLERS.get(job["kind"])
    if handlers is None:
        log.error("Dropped job with unknown kind: %s", job["kind"])
        return
    work, on_failure = handlers
    try:
        work(job["user_id"], job["payload"])
    except Exception as error:
        log.warning("Job %s failed: %s", job["kind"], type(error).__name__)
        on_failure(job["user_id"], job["payload"])


def run_once() -> bool:
    """Process one queued job. Returns False when the queue is empty."""
    # The job is claimed and committed before any model call, so a failure can never pay twice.
    # ponytail: a crash mid-job leaves that posting queued; add a lease when jobs need retries.
    with connect() as conn:
        job = conn.execute(
            """DELETE FROM jobs WHERE id = (
                   SELECT id FROM jobs j
                   -- A paused model step's work waits in the queue until the pause ends.
                   WHERE NOT EXISTS (
                       SELECT 1 FROM step_pauses p
                       WHERE p.user_id = j.user_id AND p.paused_until > now()
                         AND p.step IN (SELECT jsonb_array_elements_text(%s::jsonb -> j.kind)))
                   ORDER BY kind = %s, id FOR UPDATE SKIP LOCKED LIMIT 1
               ) RETURNING user_id, kind, payload""",
            # Eval Cases wait behind everything else, so the person's own work goes first.
            (json.dumps(gateway.JOB_STEPS), eval_runs.EVAL_CASE_JOB),
        ).fetchone()
    if job is None:
        return False
    _run(job)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    finish_interrupted_evals()
    while True:
        schedule_daily_evals(datetime.now(UTC))
        daily_clean_up(datetime.now(UTC))
        if not run_once():
            time.sleep(IDLE_SECONDS)


if __name__ == "__main__":
    main()
