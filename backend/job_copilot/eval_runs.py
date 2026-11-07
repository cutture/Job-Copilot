"""The Eval Runs page, and whether evals are failing.

It only reads stored results, so it doesn't import DeepEval. A run fails when a case whose
labels the owner has checked fails; unchecked cases show but aren't trusted yet. A run where
nothing checked passed or failed, as when the budget is used up, changes nothing.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from job_copilot.db import UserId, connect

router = APIRouter()

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
