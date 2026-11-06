"""Eval Runs: invented Eval Cases through the real Filter, rating and Pack steps.

The owner runs them by hand from the worker container:

    docker compose exec worker python -m job_copilot.evals          # run every case
    docker compose exec worker python -m job_copilot.evals show     # the latest results

Cases run as an invented person whose $3 monthly cap stops evals before anything else. A
DeepEval metric judges each outcome against the case's labels; DeepEval sends nothing anywhere.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import UUID

# DeepEval must never phone home: no telemetry, no Confident AI, no .env loading, no update
# check. These are read when DeepEval is imported, so they're set first.
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
os.environ["CONFIDENT_TRACING_ENABLED"] = "NO"
os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"
os.environ["DEEPEVAL_UPDATE_WARNING_OPT_IN"] = "0"
os.environ.pop("CONFIDENT_API_KEY", None)

from deepeval.metrics import BaseMetric  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

from job_copilot import applications, bands, filter, gateway, rating  # noqa: E402
from job_copilot.db import connect, current_user_id  # noqa: E402

EVAL_USER = UUID("00000000-0000-0000-0000-00000000e7a1")
CASES_FILE = Path(__file__).parent.parent / "evals" / "cases.json"


@dataclass
class Outcome:
    """What the real steps did with one case. Fields stay None for steps the case skips."""

    passes: bool | None = None
    filter_reason: str | None = None
    band: str | None = None
    # The Band the rules give the Requirement Results, to catch a wrong code-calculated Band.
    rules_band: str | None = None
    unmet_hard_blockers: list[str] = field(default_factory=list)
    resume: str | None = None
    letter: str | None = None


def judge(expect: dict[str, Any], outcome: Outcome) -> tuple[list[str], bool]:
    """Compare an outcome with the case's labels: what failed, and whether any is a Hard Failure."""
    failures: list[str] = []
    hard = False
    if "passes" in expect and outcome.passes != expect["passes"]:
        failures.append(
            "Filter set it aside: " + (outcome.filter_reason or "no reason")
            if expect["passes"]
            else "Filter let it through"
        )
    if "band" in expect and outcome.band != expect["band"]:
        failures.append(f"Band was {outcome.band}, labelled {expect['band']}")
        hard |= {outcome.band, expect["band"]} == {"High", "Low"}
    if outcome.band != outcome.rules_band:
        failures.append(
            f"Code-calculated Band {outcome.band} differs from the rules' {outcome.rules_band}"
        )
        hard = True
    if expect.get("hard_blocker") and not outcome.unmet_hard_blockers:
        failures.append("Missed the Hard Blocker")
        hard = True
    for key, text in (("not_in_resume", outcome.resume), ("not_in_pack", None)):
        documents = text if key == "not_in_resume" else f"{outcome.resume}\n{outcome.letter}"
        for trap in expect.get(key, []):
            if trap.casefold() in (documents or "").casefold():
                failures.append(f"An Invented Claim reached the final Pack: “{trap}”")
                hard = True
    return failures, hard


class LabelsMetric(BaseMetric):  # type: ignore[no-untyped-call]
    """Pass when the outcome matches every label of the case; any Hard Failure is recorded."""

    def __init__(self) -> None:
        self.threshold = 1.0
        self.async_mode = False
        self.hard_failure = False

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        failures, self.hard_failure = judge(
            json.loads(test_case.expected_output or "{}"), (test_case.metadata or {})["outcome"]
        )
        self.reason = "; ".join(failures) or "Matches its labels"
        self.score = 0.0 if failures else 1.0
        self.success = not failures
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self) -> str:
        return "Eval Case labels"


def _documents_text(
    resume: applications.Resume, letter: applications.CoverLetter
) -> tuple[str, str]:
    lines = [c.text for c in resume.skills + resume.education]
    lines += [c.text for role in resume.experience for c in (role.heading, *role.lines)]
    return "\n".join(lines), "\n".join(s.text for p in letter.paragraphs for s in p)


def run_case(case: dict[str, Any], profile: dict[str, Any]) -> Outcome:
    """Send one case through the real steps, as the invented eval person."""
    outcome = Outcome()
    posting = case["posting"]
    if case["area"] == "filter":
        decision = filter.decide(filter.read_facts(EVAL_USER, posting), profile["preferences"])
        outcome.passes, outcome.filter_reason = decision.passed, decision.reason
        return outcome
    evidence = dict(enumerate(profile["evidence"], start=1))
    match = rating.rate(EVAL_USER, posting, evidence, profile["facts"])
    outcome.band = match.band
    counted = [r for r in match.requirements if r.quote or r.result != "met"]
    outcome.rules_band = bands.rate(
        [bands.JudgedRequirement(r.requirement, r.kind, r.result) for r in counted],
        match.seniority,
    ).band
    outcome.unmet_hard_blockers = [
        r.requirement
        for r in match.requirements
        if r.kind == "hard_blocker" and r.result in ("missing", "unknown")
    ]
    if case["area"] in ("pack", "injection"):
        pack_evidence: dict[int, dict[str, Any]] = {
            n: {"text": text, "origin": "self_reported", "id": None} for n, text in evidence.items()
        }
        pack_evidence[applications.EDUCATION_EVIDENCE] = {
            "text": f"Education: {profile['facts']['education']}",
            "origin": "profile",
            "id": None,
        }
        requirements = [r.model_dump() for r in match.requirements]
        resume, letter, _, _ = applications.write_pack(
            EVAL_USER, posting, requirements, pack_evidence
        )
        outcome.resume, outcome.letter = _documents_text(resume, letter)
    return outcome


def run(owner: UUID, cases_file: Path = CASES_FILE) -> int:
    """Run every case, store the results, and return the Eval Run's ID."""
    loaded = json.loads(cases_file.read_text(encoding="utf-8"))
    with connect() as conn:
        run_row: Any = conn.execute(
            """INSERT INTO eval_runs (user_id, deepeval_version) VALUES (%s, %s)
               RETURNING id, started_at""",
            (owner, version("deepeval")),
        ).fetchone()
    for case in loaded["cases"]:
        metric = LabelsMetric()
        try:
            outcome = run_case(case, loaded["profile"])
            metric.measure(
                LLMTestCase(
                    input=case["posting"],
                    actual_output=json.dumps(outcome.__dict__),
                    expected_output=json.dumps(case["expect"]),
                    metadata={"outcome": outcome},
                )
            )
            status = "passed" if metric.success else "failed"
            reason = str(metric.reason)
        except gateway.GatewayError as error:
            # A timeout, rate limit or the eval budget is provider trouble, not a failure.
            status, reason = "did_not_run", f"Did not run: {error}"
        except (ValueError, KeyError, TypeError) as error:
            status, reason = (
                "failed",
                f"The model's answer couldn't be used ({type(error).__name__})",
            )
        with connect() as conn:
            conn.execute(
                """INSERT INTO eval_results (user_id, run_id, case_id, area, status, hard_failure,
                                            labels_checked, reason)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    owner,
                    run_row["id"],
                    case["id"],
                    case["area"],
                    status,
                    metric.hard_failure and status == "failed",
                    case["labels_checked"],
                    reason,
                ),
            )
    with connect() as conn:
        conn.execute(
            """UPDATE eval_runs SET finished_at = now(),
                   cost_usd = (SELECT COALESCE(sum(cost_usd), 0) FROM model_calls
                               WHERE user_id = %s AND created_at >= %s)
               WHERE id = %s AND user_id = %s""",
            (EVAL_USER, run_row["started_at"], run_row["id"], owner),
        )
    return int(run_row["id"])


def table(owner: UUID, run_id: int | None = None) -> str:
    """A plain table of one Eval Run's results; the latest run when none is named."""
    with connect() as conn:
        run_row: Any = conn.execute(
            """SELECT id, started_at, deepeval_version, cost_usd FROM eval_runs
               WHERE user_id = %s AND (%s::bigint IS NULL OR id = %s)
               ORDER BY id DESC LIMIT 1""",
            (owner, run_id, run_id),
        ).fetchone()
        if run_row is None:
            return "No Eval Runs yet."
        results = conn.execute(
            """SELECT case_id, area, status, hard_failure, labels_checked, reason
               FROM eval_results WHERE run_id = %s AND user_id = %s ORDER BY id""",
            (run_row["id"], owner),
        ).fetchall()
    hard = sum(r["hard_failure"] for r in results)
    lines = [
        f"Eval Run {run_row['id']} at {run_row['started_at']:%Y-%m-%d %H:%M} UTC, "
        f"DeepEval {run_row['deepeval_version']}, cost ${run_row['cost_usd'] or 0:.4f}",
        f"{'Case':32} {'Area':9} {'Result':12} {'Labels':10} Reason",
    ]
    for r in results:
        result = "HARD FAIL" if r["hard_failure"] else r["status"].replace("_", " ")
        labels = "checked" if r["labels_checked"] else "unchecked"
        lines.append(f"{r['case_id']:32} {r['area']:9} {result:12} {labels:10} {r['reason']}")
    lines.append(f"Hard Failures: {hard}. Results of unchecked cases aren't trusted yet.")
    return "\n".join(lines)


def main() -> None:
    owner = current_user_id()
    if sys.argv[1:] != ["show"]:
        run(owner)
    print(table(owner))


if __name__ == "__main__":
    main()
