import logging
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from job_copilot import applications, filter, profile, rating, search
from job_copilot.db import connect

log = logging.getLogger(__name__)

IDLE_SECONDS = 2.0
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
# Each kind of job, and what to record if it fails, so one failure never blocks the queue.
HANDLERS: dict[str, tuple[Handler, Handler]] = {
    "process_posting": (_process_posting_job, _posting_failed),
    "extract_evidence": (profile.extract_evidence, profile.mark_extraction_failed),
    "rate_match": (rating.rate_match, rating.mark_not_rated),
    "search": (search.run_search, search.finish_search),
    "generate_pack": (applications.generate_pack, applications.pack_failed),
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
                   SELECT id FROM jobs ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
               ) RETURNING user_id, kind, payload"""
        ).fetchone()
    if job is None:
        return False
    _run(job)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        if not run_once():
            time.sleep(IDLE_SECONDS)


if __name__ == "__main__":
    main()
