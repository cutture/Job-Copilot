"""The Eval Runs page, whether evals are failing, and starting and finishing each run.

It never runs a case, so it doesn't import DeepEval. A run fails when a case whose
labels the owner has checked fails; unchecked cases show but aren't trusted yet. A run where
nothing checked passed or failed, as when the budget is used up, changes nothing.
"""

import json
from datetime import datetime
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from job_copilot.db import EVAL_USER_ID, UserId, connect

router = APIRouter()

CASES_FILE = Path(__file__).parent.parent / "evals" / "cases.json"
# The kind of queued job that runs one Eval Case. The worker takes every other job first.
EVAL_CASE_JOB = "eval_case"
WORKER_STOPPED = "The worker stopped during this case"
NOT_RECORDED = "The worker couldn't record this case"
FIX_WORKER = "The worker: its log names the error"


def load_cases(cases_file: Path = CASES_FILE) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(cases_file.read_text(encoding="utf-8"))
    return loaded


def start_run(conn: Any, owner: UUID) -> Any:
    """A new Eval Run's row, with its id and started_at."""
    return conn.execute(
        """INSERT INTO eval_runs (user_id, deepeval_version) VALUES (%s, %s)
           RETURNING id, started_at""",
        (owner, version("deepeval")),
    ).fetchone()


def record_result(
    owner: UUID,
    run_id: int,
    case: dict[str, Any],
    status: str,
    hard_failure: bool,
    reason: str,
    fix_area: str | None,
) -> None:
    """Store one case's result, unless the run already has one for it."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO eval_results (user_id, run_id, case_id, area, status,
                                        hard_failure, labels_checked, reason, fix_area)
               SELECT %(owner)s, %(run_id)s, %(case_id)s, %(area)s, %(status)s,
                      %(hard)s, %(checked)s, %(reason)s, %(fix_area)s
               WHERE NOT EXISTS (SELECT 1 FROM eval_results
                                 WHERE user_id = %(owner)s AND run_id = %(run_id)s
                                   AND case_id = %(case_id)s)""",
            {
                "owner": owner,
                "run_id": run_id,
                "case_id": case["id"],
                "area": case["area"],
                "status": status,
                "hard": hard_failure,
                "checked": case["labels_checked"],
                "reason": reason,
                "fix_area": fix_area,
            },
        )


def queue_daily_run(owner: UUID, now: datetime, cases_file: Path = CASES_FILE) -> None:
    """Start today's Eval Run as one job per case, unless a run already started today."""
    case_ids = [case["id"] for case in load_cases(cases_file)["cases"]]
    with connect() as conn:
        # One run a day, even across restarts: the run's row exists from the moment it's queued.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('daily eval run'))")
        started_today = conn.execute(
            # The day starts at midnight UTC, whatever the database's time zone.
            """SELECT 1 FROM eval_runs WHERE user_id = %(owner)s
               AND started_at >= date_trunc('day', %(now)s::timestamptz AT TIME ZONE 'UTC')
                                 AT TIME ZONE 'UTC'""",
            {"owner": owner, "now": now},
        ).fetchone()
        if started_today:
            return
        run = start_run(conn, owner)
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO jobs (user_id, kind, payload) VALUES (%s, %s, %s)",
                [
                    (owner, EVAL_CASE_JOB, json.dumps({"run_id": run["id"], "case_id": case_id}))
                    for case_id in case_ids
                ],
            )


def case_not_recorded(owner: UUID, run_id: int, case_id: str) -> None:
    """A case job that failed outside its case still shows in its run, as failed."""
    try:
        for case in load_cases()["cases"]:
            if case["id"] == case_id:
                record_result(owner, run_id, case, "failed", False, NOT_RECORDED, FIX_WORKER)
    finally:
        finish_runs(owner, run_id)


def finish_interrupted_runs(owner: UUID, cases_file: Path = CASES_FILE) -> None:
    """When the worker starts: finish runs a crash left open, each missing case as not run.

    ponytail: a run started by hand, from the command line, is open with no queued cases too,
    so a worker restart while it runs finishes it early; mark runs started by hand if that bites.
    """
    with connect() as conn:
        open_runs = conn.execute(
            """SELECT r.id FROM eval_runs r
               WHERE r.user_id = %s AND r.finished_at IS NULL
                 AND NOT EXISTS (SELECT 1 FROM jobs j
                                 WHERE j.user_id = r.user_id AND j.kind = %s
                                   AND (j.payload ->> 'run_id')::bigint = r.id)""",
            (owner, EVAL_CASE_JOB),
        ).fetchall()
    cases = load_cases(cases_file)["cases"]
    for run in open_runs:
        for case in cases:
            record_result(owner, run["id"], case, "did_not_run", False, WORKER_STOPPED, None)
        finish_runs(owner, run["id"])


def finish_runs(owner: UUID, run_id: int) -> None:
    """Finish the run once no case of it is left queued."""
    with connect() as conn:
        conn.execute(
            # ponytail: a run's cost is all eval spending since it started, so two runs at
            # once would count each other's; tag model calls with their run if they overlap.
            """UPDATE eval_runs r SET finished_at = now(),
                   cost_usd = (SELECT COALESCE(sum(cost_usd), 0) FROM model_calls
                               WHERE user_id = %(eval_user)s AND created_at >= r.started_at)
               WHERE r.user_id = %(owner)s AND r.id = %(run_id)s AND r.finished_at IS NULL
                 AND NOT EXISTS (SELECT 1 FROM jobs j
                                 WHERE j.user_id = r.user_id AND j.kind = %(kind)s
                                   AND (j.payload ->> 'run_id')::bigint = r.id)""",
            {"eval_user": EVAL_USER_ID, "owner": owner, "run_id": run_id, "kind": EVAL_CASE_JOB},
        )


# Each finished run's verdict: failing, passing, or neither when nothing checked was judged.
RUN_VERDICTS = """
    SELECT r.id, r.finished_at,
           bool_or(e.labels_checked AND e.status = 'failed') AS failing,
           bool_or(e.labels_checked AND e.status = 'passed') AS judged
    FROM eval_runs r
    LEFT JOIN eval_results e ON e.run_id = r.id AND e.user_id = r.user_id
    WHERE r.user_id = %(user_id)s AND r.finished_at IS NOT NULL
    GROUP BY r.id, r.finished_at
"""


class EvalRunSummary(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    cost_usd: Decimal | None
    passed: int
    failed: int
    did_not_run: int
    hard_failures: int
    # Results of cases whose labels the owner hasn't checked yet.
    unchecked: int


class EvalCaseResult(BaseModel):
    case_id: str
    area: str
    status: str
    hard_failure: bool
    labels_checked: bool
    reason: str
    # Where to look first to fix a failure.
    fix_area: str | None


class EvalRun(EvalRunSummary):
    deepeval_version: str
    results: list[EvalCaseResult]


class EvalStatus(BaseModel):
    failing: bool
    # When the current failing streak began; Packs made since then need extra care.
    failing_since: datetime | None


SUMMARY = """
    SELECT r.id, r.started_at, r.finished_at, r.cost_usd, r.deepeval_version,
           count(*) FILTER (WHERE e.status = 'passed') AS passed,
           count(*) FILTER (WHERE e.status = 'failed') AS failed,
           count(*) FILTER (WHERE e.status = 'did_not_run') AS did_not_run,
           count(*) FILTER (WHERE e.hard_failure) AS hard_failures,
           count(*) FILTER (WHERE NOT e.labels_checked) AS unchecked
    FROM eval_runs r
    LEFT JOIN eval_results e ON e.run_id = r.id AND e.user_id = r.user_id
    WHERE r.user_id = %(user_id)s AND (%(run_id)s::bigint IS NULL OR r.id = %(run_id)s)
    GROUP BY r.id
    ORDER BY r.id DESC
"""


@router.get("/api/eval-runs")
def list_eval_runs(user_id: UserId) -> list[EvalRunSummary]:
    with connect() as conn:
        rows = conn.execute(SUMMARY + " LIMIT 60", {"user_id": user_id, "run_id": None}).fetchall()
    return [EvalRunSummary(**row) for row in rows]


@router.get("/api/eval-runs/{run_id}")
def get_eval_run(run_id: int, user_id: UserId) -> EvalRun:
    with connect() as conn:
        row: Any = conn.execute(SUMMARY, {"user_id": user_id, "run_id": run_id}).fetchone()
        if row is None:
            raise HTTPException(404, "Eval Run not found")
        results = conn.execute(
            """SELECT case_id, area, status, hard_failure, labels_checked, reason, fix_area
               FROM eval_results WHERE run_id = %s AND user_id = %s ORDER BY id""",
            (run_id, user_id),
        ).fetchall()
    return EvalRun(**row, results=[EvalCaseResult(**r) for r in results])


def eval_status(conn: Any, user_id: UUID) -> EvalStatus:
    """Whether the latest judged run failed, and since when evals have been failing."""
    runs = conn.execute(
        f"SELECT * FROM ({RUN_VERDICTS}) v WHERE failing OR judged ORDER BY finished_at",
        {"user_id": user_id},
    ).fetchall()
    since = None
    for run in runs:
        if run["failing"]:
            since = since or run["finished_at"]
        else:
            since = None
    return EvalStatus(failing=since is not None, failing_since=since)


@router.get("/api/evals/status")
def get_eval_status(user_id: UserId) -> EvalStatus:
    with connect() as conn:
        return eval_status(conn, user_id)
