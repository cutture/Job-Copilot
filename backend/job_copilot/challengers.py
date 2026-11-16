"""Model recommendations: a Challenger that qualifies for a model step, and the owner approving
it or switching back.

A Challenger qualifies after three Challenger runs about a week apart with no Hard Failures,
which do no worse than the current model on any of the step's judged scores, in the same weeks
and on the same models for every other step, and better on one; a Verification Challenger must
be better at catching Traps. It must be able to take the step's data now, and last month's
total, with that step repriced at its rates, must fit the monthly cap. Nothing switches until
the owner approves.
"""

from datetime import timedelta
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
# Challenger runs count only when this far apart, so three come from three weeks.
RUNS_APART = timedelta(days=6)
# The scores that judge each step, and whether higher is better.
STEP_SCORES = {
    "rating": {"Exact Band": True, "Requirement Results": True},
    "pack": {"Writer invention rate": False, "Stretched Claims": False},
    "verification": {"Traps caught": True, "Wrong removals": False},
}
# A step whose Challenger must win on this score, not any: Verification must catch more.
MUST_BE_BETTER_ON = {"verification": "Traps caught"}
# How far back spending is priced for the cost check.
USE_DAYS = 30


class ScoreComparison(BaseModel):
    score: str
    # Averages over the runs compared, as percentages.
    challenger: float
    current: float


class ModelRecommendation(BaseModel):
    step: str
    label: str
    model: str
    model_name: str
    current_name: str
    runs: list[int]
    compared: list[ScoreComparison]
    # Last month's total spending, with this step repriced at the Challenger's rates.
    projected_monthly_usd: Decimal


class Choice(BaseModel):
    step: str
    model: str


class StepModel(BaseModel):
    step: str
    label: str
    model_name: str
    # Whether the owner approved this model, rather than it being the step's default.
    approved: bool


def _models_of(conn: Any, owner: UUID, run_id: int) -> dict[str, str] | None:
    """The model each step used across a run, or None if some step used more than one."""
    rows = conn.execute(
        "SELECT models FROM eval_results WHERE run_id = %s AND user_id = %s AND models IS NOT NULL",
        (run_id, owner),
    ).fetchall()
    seen: dict[str, set[str]] = {}
    for row in rows:
        for step, model in row["models"].items():
            seen.setdefault(step, set()).add(model)
    if any(len(models) > 1 for models in seen.values()):
        return None
    return {step: models.pop() for step, models in seen.items()}


def _same_other_steps(a: dict[str, str], b: dict[str, str], step: str) -> bool:
    return all(a[s] == b[s] for s in a.keys() & b.keys() if s != step)


def _weekly(runs: list[Any]) -> list[Any]:
    """The newest runs, keeping only those about a week before the one kept after them."""
    kept: list[Any] = []
    for run in runs:
        if not kept or kept[-1]["started_at"] - run["started_at"] >= RUNS_APART:
            kept.append(run)
    return kept[:RUNS_NEEDED]


def _averages(conn: Any, owner: UUID, run_ids: list[int], names: set[str]) -> dict[str, float]:
    values: dict[str, list[int]] = {name: [] for name in names}
    for run_id in run_ids:
        for score in eval_runs.run_tracked_scores(conn, owner, run_id):
            if score.name in names and score.value is not None:
                values[score.name].append(score.value)
    return {name: mean(found) for name, found in values.items() if found}


def _projected_monthly(conn: Any, owner: UUID, challenger: gateway.Challenger) -> Decimal:
    """Last month's total spending, with the step's own calls repriced at the Challenger's rates."""
    calls = [name for name, step in gateway.STEP_OF.items() if step == challenger.step]
    spent: Any = conn.execute(
        f"""SELECT COALESCE(sum(cost_usd), 0) AS total,
                   COALESCE(sum(cost_usd) FILTER (WHERE user_id = %(owner)s
                                                    AND step = ANY(%(calls)s)), 0) AS step_cost,
                   COALESCE(sum(input_tokens) FILTER (WHERE user_id = %(owner)s
                                                        AND step = ANY(%(calls)s)), 0) AS input,
                   COALESCE(sum(output_tokens) FILTER (WHERE user_id = %(owner)s
                                                         AND step = ANY(%(calls)s)), 0) AS output
            FROM model_calls WHERE user_id = ANY(%(spenders)s)
              AND created_at > now() - interval '{USE_DAYS} days'""",
        {"owner": owner, "calls": calls, "spenders": list(gateway.spenders(owner))},
    ).fetchone()
    repriced = gateway.price_of(gateway.MODELS[challenger.model], spent["input"], spent["output"])
    projected: Decimal = spent["total"] - spent["step_cost"] + repriced
    return projected


def _recommendation(
    conn: Any, owner: UUID, challenger: gateway.Challenger
) -> ModelRecommendation | None:
    step, model = challenger
    if gateway.approved_model(owner, step) == model or not gateway.can_take_personal(owner, model):
        return None
    tried = conn.execute(
        f"""SELECT * FROM ({eval_runs.SUMMARY}) s
            WHERE challenger_step = %(step)s AND challenger_model = %(model)s
              AND finished_at IS NOT NULL
            ORDER BY started_at DESC""",
        {"user_id": owner, "run_id": None, "step": step, "model": model},
    ).fetchall()
    challenger_runs = _weekly(tried)
    if len(challenger_runs) < RUNS_NEEDED or any(r["hard_failures"] for r in challenger_runs):
        return None
    dismissed = conn.execute(
        """SELECT 1 FROM dismissed_recommendations
           WHERE user_id = %s AND step = %s AND model = %s AND dismissed_at >= %s""",
        (owner, step, model, max(r["finished_at"] for r in challenger_runs)),
    ).fetchone()
    if dismissed:
        return None
    challenger_models = [_models_of(conn, owner, r["id"]) for r in challenger_runs]
    if any(m is None for m in challenger_models):
        return None
    since = min(r["started_at"] for r in challenger_runs)
    regular = conn.execute(
        """SELECT id FROM eval_runs WHERE user_id = %s AND challenger_model IS NULL
           AND finished_at IS NOT NULL AND started_at >= %s ORDER BY id DESC""",
        (owner, since),
    ).fetchall()
    regular_models = [(r["id"], _models_of(conn, owner, r["id"])) for r in regular]
    current = next((m[step] for _, m in regular_models if m and step in m), None)
    if current is None or current == model:
        return None
    # Compared only on the same models: the step's current one, and every other step's.
    current_runs = [
        run_id
        for run_id, used in regular_models
        if used
        and used.get(step) == current
        and all(_same_other_steps(used, c or {}, step) for c in challenger_models)
    ]
    judged = STEP_SCORES[step]
    theirs = _averages(conn, owner, [r["id"] for r in challenger_runs], set(judged))
    ours = _averages(conn, owner, current_runs, set(judged))
    compared = [name for name in judged if name in theirs and name in ours]

    def ahead(name: str, of: dict[str, float], than: dict[str, float]) -> bool:
        return of[name] > than[name] if judged[name] else of[name] < than[name]

    if not compared or any(ahead(n, ours, theirs) for n in compared):
        return None
    must = MUST_BE_BETTER_ON.get(step)
    better_on = [must] if must else compared
    if not any(n in compared and ahead(n, theirs, ours) for n in better_on):
        return None
    projected = _projected_monthly(conn, owner, challenger)
    cap, _ = gateway.cap_and_spent(conn, owner)
    if projected > cap:
        return None
    return ModelRecommendation(
        step=step,
        label=gateway.STEP_LABELS[step],
        model=model,
        model_name=gateway.model_name(model),
        current_name=gateway.model_name(current),
        runs=[r["id"] for r in challenger_runs],
        compared=[
            ScoreComparison(score=n, challenger=theirs[n], current=ours[n]) for n in compared
        ],
        projected_monthly_usd=projected,
    )


def recommendations(owner: UUID) -> list[ModelRecommendation]:
    with connect() as conn:
        tried = conn.execute(
            """SELECT DISTINCT challenger_step AS step, challenger_model AS model FROM eval_runs
               WHERE user_id = %s AND challenger_step = ANY(%s)""",
            (owner, list(eval_runs.CHALLENGER_STEPS)),
        ).fetchall()
        found = [
            _recommendation(conn, owner, gateway.Challenger(r["step"], r["model"])) for r in tried
        ]
    return [r for r in found if r]


@router.get("/api/model-recommendations")
def get_recommendations(user_id: UserId) -> list[ModelRecommendation]:
    return recommendations(user_id)


@router.post("/api/model-recommendations/approve")
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


@router.post("/api/model-recommendations/dismiss")
def dismiss(choice: Choice, user_id: UserId) -> list[ModelRecommendation]:
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
    for step in eval_runs.CHALLENGER_STEPS:
        approved = gateway.approved_model(user_id, step)
        in_use = approved or gateway.PERSONAL_MODELS[0]
        shown.append(
            StepModel(
                step=step,
                label=gateway.STEP_LABELS[step],
                model_name=gateway.model_name(in_use),
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
