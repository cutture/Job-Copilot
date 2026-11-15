"""Recommending a Challenger for a model step, and the owner approving it or switching back.

A Challenger qualifies after three Challenger runs with no Hard Failures that do no worse than
the current model on any of the step's judged scores, in the same weeks, and better on one; it
must be eligible for the step's data, and last month's use of the step at its prices must fit
the monthly cap. Nothing switches until the owner approves.
"""

from datetime import datetime
from decimal import Decimal
from statistics import mean
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from job_copilot import eval_runs, gateway
from job_copilot.db import UserId, connect

router = APIRouter()

RUNS_NEEDED = 3
# The steps a Challenger can take over, with the scores that judge each, and whether higher is
# better.
STEP_SCORES = {
    "rating": {"Exact Band": True, "Requirement Results": True},
    "pack": {"Writer invention rate": False, "Stretched Claims": False},
}
STEP_LABELS = {"rating": "Rating Matches", "pack": "Writing Application Packs"}
# How far back a step's own use is priced for the cost check.
USE_DAYS = 30


class Evidence(BaseModel):
    score: str
    # Averages over the runs compared, as percentages.
    challenger: float
    current: float


class Recommendation(BaseModel):
    step: str
    model: str
    model_name: str
    current_name: str
    runs: list[int]
    evidence: list[Evidence]
    # Last month's use of the step, at the Challenger's prices.
    monthly_cost_usd: Decimal


class Choice(BaseModel):
    step: str
    model: str


class StepModel(BaseModel):
    step: str
    label: str
    model_name: str
    # Whether the owner approved this model, rather than it being the step's default.
    approved: bool


def _model_used(conn: Any, owner: UUID, run_id: int, step: str) -> str | None:
    """The one model a run used for this step, or None if it used several or none."""
    rows = conn.execute(
        """SELECT DISTINCT models ->> %s AS model FROM eval_results
           WHERE run_id = %s AND user_id = %s AND models ? %s""",
        (step, run_id, owner, step),
    ).fetchall()
    return rows[0]["model"] if len(rows) == 1 else None


def _averages(conn: Any, owner: UUID, run_ids: list[int], names: set[str]) -> dict[str, float]:
    values: dict[str, list[int]] = {name: [] for name in names}
    for run_id in run_ids:
        for score in eval_runs.run_tracked_scores(conn, owner, run_id):
            if score.name in names and score.value is not None:
                values[score.name].append(score.value)
    return {name: mean(found) for name, found in values.items() if found}


def _monthly_cost(conn: Any, owner: UUID, step: str, model: str) -> Decimal:
    calls = [name for name, group in gateway.STEP_OF.items() if group == step]
    used: Any = conn.execute(
        f"""SELECT COALESCE(sum(input_tokens), 0) AS input,
                   COALESCE(sum(output_tokens), 0) AS output
            FROM model_calls WHERE user_id = %s AND step = ANY(%s)
              AND created_at > now() - interval '{USE_DAYS} days'""",
        (owner, calls),
    ).fetchone()
    return gateway.price_of(gateway.MODELS[model], used["input"], used["output"])


def _recommendation(conn: Any, owner: UUID, step: str, model: str) -> Recommendation | None:
    if gateway.approved_model(owner, step) == model:
        return None
    if gateway.DataClass.PERSONAL not in gateway.MODELS[model].data_classes:
        return None
    challenger_runs = conn.execute(
        f"""SELECT * FROM ({eval_runs.SUMMARY}) s
            WHERE challenger_step = %(step)s AND challenger_model = %(model)s
              AND finished_at IS NOT NULL
            ORDER BY finished_at DESC LIMIT {RUNS_NEEDED}""",
        {"user_id": owner, "run_id": None, "step": step, "model": model},
    ).fetchall()
    if len(challenger_runs) < RUNS_NEEDED or any(r["hard_failures"] for r in challenger_runs):
        return None
    dismissed = conn.execute(
        """SELECT 1 FROM dismissed_recommendations
           WHERE user_id = %s AND step = %s AND model = %s AND dismissed_at >= %s""",
        (owner, step, model, challenger_runs[0]["finished_at"]),
    ).fetchone()
    if dismissed:
        return None
    since: datetime = min(r["started_at"] for r in challenger_runs)
    regular = conn.execute(
        """SELECT id FROM eval_runs WHERE user_id = %s AND challenger_model IS NULL
           AND finished_at IS NOT NULL AND started_at >= %s ORDER BY id DESC""",
        (owner, since),
    ).fetchall()
    current = next((m for r in regular if (m := _model_used(conn, owner, r["id"], step))), None)
    # Compared only with runs on the same model: the one the step uses now.
    current_runs = [r["id"] for r in regular if _model_used(conn, owner, r["id"], step) == current]
    if current is None or current == model:
        return None
    judged = STEP_SCORES[step]
    theirs = _averages(conn, owner, [r["id"] for r in challenger_runs], set(judged))
    ours = _averages(conn, owner, current_runs, set(judged))
    compared = [name for name in judged if name in theirs and name in ours]

    def better(name: str) -> bool:
        return theirs[name] > ours[name] if judged[name] else theirs[name] < ours[name]

    def worse(name: str) -> bool:
        return theirs[name] < ours[name] if judged[name] else theirs[name] > ours[name]

    if not compared or any(map(worse, compared)) or not any(map(better, compared)):
        return None
    cost = _monthly_cost(conn, owner, step, model)
    cap, _ = gateway.cap_and_spent(conn, owner)
    if cost > cap:
        return None
    return Recommendation(
        step=step,
        model=model,
        model_name=gateway.model_name(model),
        current_name=gateway.model_name(current),
        runs=[r["id"] for r in challenger_runs],
        evidence=[Evidence(score=n, challenger=theirs[n], current=ours[n]) for n in compared],
        monthly_cost_usd=cost,
    )


def recommendations(owner: UUID) -> list[Recommendation]:
    with connect() as conn:
        tried = conn.execute(
            """SELECT DISTINCT challenger_step AS step, challenger_model AS model FROM eval_runs
               WHERE user_id = %s AND challenger_step = ANY(%s)""",
            (owner, list(STEP_SCORES)),
        ).fetchall()
        found = [_recommendation(conn, owner, r["step"], r["model"]) for r in tried]
    return [r for r in found if r]


@router.get("/api/recommendations")
def get_recommendations(user_id: UserId) -> list[Recommendation]:
    return recommendations(user_id)


@router.post("/api/recommendations/approve")
def approve(choice: Choice, user_id: UserId) -> list[StepModel]:
    """Use the recommended model for its step, and check it with an Eval Run straight away."""
    if not any((r.step, r.model) == (choice.step, choice.model) for r in recommendations(user_id)):
        raise HTTPException(409, "That model isn't recommended for this step now.")
    with connect() as conn:
        conn.execute(
            """INSERT INTO step_models (user_id, step, model) VALUES (%s, %s, %s)
               ON CONFLICT (user_id, step) DO UPDATE SET model = excluded.model,
                                                         approved_at = now()""",
            (user_id, choice.step, choice.model),
        )
    eval_runs.queue_run_now(user_id)
    return get_step_models(user_id)


@router.post("/api/recommendations/dismiss")
def dismiss(choice: Choice, user_id: UserId) -> list[Recommendation]:
    with connect() as conn:
        conn.execute(
            """INSERT INTO dismissed_recommendations (user_id, step, model) VALUES (%s, %s, %s)
               ON CONFLICT (user_id, step, model) DO UPDATE SET dismissed_at = now()""",
            (user_id, choice.step, choice.model),
        )
    return recommendations(user_id)


@router.get("/api/step-models")
def get_step_models(user_id: UserId) -> list[StepModel]:
    """Each step a Challenger can take over, and the model it starts with now."""
    shown = []
    for step, label in STEP_LABELS.items():
        approved = gateway.approved_model(user_id, step)
        first = approved or gateway.PERSONAL_MODELS[0]
        shown.append(
            StepModel(
                step=step,
                label=label,
                model_name=gateway.model_name(first),
                approved=approved is not None,
            )
        )
    return shown


@router.delete("/api/step-models/{step}")
def switch_back(step: str, user_id: UserId) -> list[StepModel]:
    """Go back to the step's default model, and check it with an Eval Run straight away."""
    with connect() as conn:
        removed = conn.execute(
            "DELETE FROM step_models WHERE user_id = %s AND step = %s", (user_id, step)
        ).rowcount
    if removed:
        eval_runs.queue_run_now(user_id)
    return get_step_models(user_id)
