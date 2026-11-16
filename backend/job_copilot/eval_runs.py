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

from job_copilot import gateway
from job_copilot.db import EVAL_USER_ID, UserId, connect
from job_copilot.tracked_scores import CaseScores, TrackedScore, scores_for

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


# Challengers tried weekly; Sonnet elsewhere runs by hand, at about $0.70 a run.
CHALLENGERS = (
    gateway.Challenger("rating", gateway.GROQ_PERSONAL),
    gateway.Challenger("pack", gateway.GROQ_PERSONAL),
    # Paid: about $0.15 a run, with writing on Haiku, or $0.60 a month.
    gateway.Challenger("verification", gateway.SONNET),
)
CHALLENGER_EVERY_DAYS = 7
# The model steps a Challenger can take over; all handle personal data.
CHALLENGER_STEPS = ("rating", "pack", "verification")
# Labels on a case that writes a Pack, and the ones a rating Challenger is judged on.
PACK_LABELS = {"not_in_resume", "not_in_pack", "in_pack"}
RATING_LABELS = {"band", "hard_blocker", "requirements"}
Challenger = gateway.Challenger


def uses_step(case: dict[str, Any], step: str) -> bool:
    """Whether a case reaches this model step: Filter-only cases never rate, and only cases
    labelled with what a Pack may hold write and verify one."""
    if step == "rating":
        return "passes" not in case["expect"]
    return bool(PACK_LABELS & case["expect"].keys())


def for_challenger(case: dict[str, Any], challenger: Challenger | None) -> dict[str, Any]:
    """The case as a Challenger runs it: a rating Challenger stops after rating, so it's judged
    on its rating labels only and writes no Pack."""
    if challenger is None or challenger.step != "rating":
        return case
    return {**case, "expect": {k: v for k, v in case["expect"].items() if k in RATING_LABELS}}


def start_run(conn: Any, owner: UUID, challenger: Challenger | None = None) -> Any:
    """A new Eval Run's row, with its id and started_at."""
    step, model = challenger or (None, None)
    return conn.execute(
        """INSERT INTO eval_runs (user_id, deepeval_version, challenger_step, challenger_model)
           VALUES (%s, %s, %s, %s) RETURNING id, started_at""",
        (owner, version("deepeval"), step, model),
    ).fetchone()


def challenger_of(owner: UUID, run_id: int) -> Challenger | None:
    with connect() as conn:
        row: Any = conn.execute(
            """SELECT challenger_step, challenger_model FROM eval_runs
               WHERE id = %s AND user_id = %s""",
            (run_id, owner),
        ).fetchone()
    if row is None or row["challenger_step"] is None:
        return None
    return Challenger(row["challenger_step"], row["challenger_model"])


def _queue_cases(conn: Any, owner: UUID, run_id: int, case_ids: list[str]) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO jobs (user_id, kind, payload) VALUES (%s, %s, %s)",
            [
                (owner, EVAL_CASE_JOB, json.dumps({"run_id": run_id, "case_id": case_id}))
                for case_id in case_ids
            ],
        )


def record_result(
    owner: UUID,
    run_id: int,
    case: dict[str, Any],
    status: str,
    hard_failure: bool,
    reason: str,
    fix_area: str | None,
    scores: CaseScores | None = None,
    models: dict[str, str] | None = None,
) -> None:
    """Store one case's result, unless the run already has one for it."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO eval_results (user_id, run_id, case_id, area, status,
                                        hard_failure, labels_checked, reason, fix_area,
                                        scores, scores_checked, models)
               SELECT %(owner)s, %(run_id)s, %(case_id)s, %(area)s, %(status)s,
                      %(hard)s, %(checked)s, %(reason)s, %(fix_area)s,
                      %(scores)s, %(scores_checked)s, %(models)s
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
                "scores": scores and scores.model_dump_json(),
                # Only labels added for Tracked Scores wait for the owner's check.
                "scores_checked": case.get("scores_checked", True),
                "models": json.dumps(models) if models else None,
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
               AND challenger_model IS NULL
               AND started_at >= date_trunc('day', %(now)s::timestamptz AT TIME ZONE 'UTC')
                                 AT TIME ZONE 'UTC'""",
            {"owner": owner, "now": now},
        ).fetchone()
        if started_today:
            return
        _queue_cases(conn, owner, start_run(conn, owner)["id"], case_ids)


def queue_run_now(owner: UUID, cases_file: Path = CASES_FILE) -> None:
    """Start an Eval Run on the person's models now, as when a step's model changes."""
    case_ids = [case["id"] for case in load_cases(cases_file)["cases"]]
    with connect() as conn:
        _queue_cases(conn, owner, start_run(conn, owner)["id"], case_ids)


def queue_challenger_runs(owner: UUID, now: datetime, cases_file: Path = CASES_FILE) -> None:
    """Start each free Challenger's weekly run, on the cases that use its step.

    A Challenger already approved for its step, or one that may not take the step's data yet,
    such as Groq before Zero Data Retention is confirmed, isn't run.
    """
    cases = load_cases(cases_file)["cases"]
    for challenger in CHALLENGERS:
        step, model = challenger
        if gateway.approved_model(owner, step) == model or not gateway.can_take_personal(
            owner, model
        ):
            continue
        with connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('challenger run'))")
            recent = conn.execute(
                """SELECT 1 FROM eval_runs WHERE user_id = %s
                   AND challenger_step = %s AND challenger_model = %s
                   AND started_at > %s::timestamptz - %s * interval '1 day'""",
                (owner, step, model, now, CHALLENGER_EVERY_DAYS),
            ).fetchone()
            if recent:
                continue
            run = start_run(conn, owner, challenger)
            _queue_cases(conn, owner, run["id"], [c["id"] for c in cases if uses_step(c, step)])


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
      -- A Challenger's results never turn on the banner or Extra care.
      AND r.challenger_model IS NULL
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
    # The step and model a Challenger run tried; None for the person's own models.
    challenger_step: str | None = None
    challenger_label: str | None = None
    challenger_name: str | None = None


class EvalCaseResult(BaseModel):
    case_id: str
    area: str
    status: str
    hard_failure: bool
    labels_checked: bool
    reason: str
    # Where to look first to fix a failure.
    fix_area: str | None
    # The model each step used, both named for the person.
    models: dict[str, str] | None = None


class EvalRun(EvalRunSummary):
    deepeval_version: str
    results: list[EvalCaseResult]
    # How well each step did across the run's checked cases, beside its Hard Failures.
    tracked_scores: list[TrackedScore]


class EvalStatus(BaseModel):
    failing: bool
    # When the current failing streak began; Packs made since then need extra care.
    failing_since: datetime | None


SUMMARY = """
    SELECT r.id, r.started_at, r.finished_at, r.cost_usd, r.deepeval_version,
           r.challenger_step, r.challenger_model,
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
    return [EvalRunSummary(**_with_challenger_named(row)) for row in rows]


def _with_challenger_named(row: Any) -> dict[str, Any]:
    """A run's row with its Challenger's step and model named for the person."""
    step, model = row["challenger_step"], row["challenger_model"]
    return {
        **row,
        "challenger_label": step and gateway.STEP_LABELS.get(step, step),
        "challenger_name": model and gateway.model_name(model),
    }


@router.get("/api/eval-runs/{run_id}")
def get_eval_run(run_id: int, user_id: UserId) -> EvalRun:
    with connect() as conn:
        row: Any = conn.execute(SUMMARY, {"user_id": user_id, "run_id": run_id}).fetchone()
        if row is None:
            raise HTTPException(404, "Eval Run not found")
        results = conn.execute(
            """SELECT case_id, area, status, hard_failure, labels_checked, reason, fix_area,
                      scores, scores_checked, models
               FROM eval_results WHERE run_id = %s AND user_id = %s ORDER BY id""",
            (run_id, user_id),
        ).fetchall()
    return EvalRun(
        **_with_challenger_named(row),
        results=[
            EvalCaseResult(
                **{
                    **r,
                    "models": r["models"]
                    and {
                        gateway.STEP_LABELS.get(step, step): gateway.model_name(m)
                        for step, m in r["models"].items()
                    },
                }
            )
            for r in results
        ],
        tracked_scores=_scores_of(results),
    )


def _scores_of(results: list[Any]) -> list[TrackedScore]:
    counted = [
        {**r, "scores": CaseScores.model_validate(r["scores"])} for r in results if r["scores"]
    ]
    return scores_for(counted)


def run_tracked_scores(conn: Any, owner: UUID, run_id: int) -> list[TrackedScore]:
    """One run's Tracked Scores."""
    results = conn.execute(
        """SELECT labels_checked, scores, scores_checked FROM eval_results
           WHERE run_id = %s AND user_id = %s""",
        (run_id, owner),
    ).fetchall()
    return _scores_of(results)


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
