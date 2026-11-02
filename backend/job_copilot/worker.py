import time

from job_copilot.db import connect

IDLE_SECONDS = 2.0


def run_once() -> bool:
    """Process one queued job. Returns False when the queue is empty."""
    with connect() as conn:
        # The job and its work commit together, so a crash puts the job back on the queue.
        job = conn.execute(
            """DELETE FROM jobs WHERE id = (
                   SELECT id FROM jobs ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
               ) RETURNING user_id, kind, payload"""
        ).fetchone()
        if job is None:
            return False
        # ponytail: an unknown kind blocks the queue; add failed-job handling with the second kind.
        if job["kind"] != "process_posting":
            raise ValueError(f"Unknown job kind: {job['kind']}")
        conn.execute(
            "UPDATE job_postings SET status = 'received' WHERE id = %s AND user_id = %s",
            (job["payload"]["job_posting_id"], job["user_id"]),
        )
    return True


def main() -> None:
    while True:
        if not run_once():
            time.sleep(IDLE_SECONDS)


if __name__ == "__main__":
    main()
