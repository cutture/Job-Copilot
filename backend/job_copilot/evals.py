"""Eval Runs: invented Eval Cases through the real Filter, rating and Pack steps.

The worker runs every case once a day, after EVAL_HOUR_UTC; the owner can also run them by hand:

    docker compose exec worker python -m job_copilot.evals          # run every case now
    docker compose exec worker python -m job_copilot.evals show     # the latest results

Cases run as an invented person whose $3 monthly cap stops evals before anything else. A
DeepEval metric judges each outcome against the case's labels; DeepEval sends nothing anywhere.
A wrong code-calculated Band is caught by the Band rule tests, which run with every change.
"""

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal, NamedTuple
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
from job_copilot.db import EVAL_USER_ID, connect, current_user_id  # noqa: E402

log = logging.getLogger(__name__)

EVAL_USER = EVAL_USER_ID
CASES_FILE = Path(__file__).parent.parent / "evals" / "cases.json"
# Provider trouble that means a case didn't run, as opposed to an answer that failed it.
DID_NOT_RUN = ("Timeout", "RateLimit")
Status = Literal["passed", "failed", "did_not_run"]
# Where to look first for each kind of failure.
FIX_FILTER = "Filter: its prompt in filter.py, or its location and pay rules"
FIX_BAND = "Rating: its prompt in rating.py; the Band rules have their own code tests"
FIX_HARD_BLOCKER = "Rating: which Requirements its prompt classes as Hard Blockers, in rating.py"
FIX_PACK = "Application Pack: the writer prompts, then Verification, in applications.py"
FIX_MODEL = "The model gateway or provider, in gateway.py"
FIX_ANSWER = "The step's prompt, so the model answers in the expected shape"
FIX_VERIFY = "Verification: it removed a Claim the Evidence supports, in applications.py"
FIX_CRASH = "The step's code: the worker log names the error"
# A sentence that denies a trap, such as "I don't hold the AWS certification yet", claims nothing.
NEGATION = re.compile(
    r"\b(?:not|no|never|don't|doesn't|haven't|hasn't|without|yet to|rather than|instead of)\b",
    re.IGNORECASE,
)


@dataclass
class Outcome:
    """What the real steps did with one case. Fields stay empty for steps the case skips."""

    passes: bool | None = None
    filter_reason: str | None = None
    band: bands.Band | None = None
    # The rating's own reasons and gaps, so a wrong Band can be traced.
    band_reasons: list[str] = field(default_factory=list)
    missing_hard_blockers: list[str] = field(default_factory=list)
    resume: str = ""
    letter: str = ""


def _mentions(text: str, phrase: str) -> bool:
    """A whole-word match, so "Rust" doesn't match "trust"."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE) is not None


class Verdict(NamedTuple):
    """What failed, whether any of it is a Hard Failure, and where to look first to fix it."""

    failures: list[str]
    hard: bool
    fix_area: str | None


def _claims(documents: str, trap: str) -> bool:
    """Whether a line of the documents claims the trap, rather than saying it's lacking."""
    return any(
        _mentions(line, trap) and not NEGATION.search(line) for line in documents.splitlines()
    )


def judge(expect: dict[str, Any], outcome: Outcome) -> Verdict:
    """Compare an outcome with the case's labels."""
    failures: list[str] = []
    fixes: list[str] = []
    hard = False
    if "passes" in expect and outcome.passes != expect["passes"]:
        failures.append(
            "Filter set it aside: " + (outcome.filter_reason or "no reason")
            if expect["passes"]
            else "Filter let it through"
        )
        fixes.append(FIX_FILTER)
    if "band" in expect and outcome.band != expect["band"]:
        failures.append(
            f"Band was {outcome.band}, labelled {expect['band']} "
            f"({'; '.join(outcome.band_reasons)})"
        )
        fixes.append(FIX_BAND)
        hard |= {outcome.band, expect["band"]} == {"High", "Low"}
    if expect.get("hard_blocker") and not outcome.missing_hard_blockers:
        failures.append("Missed the Hard Blocker")
        fixes.append(FIX_HARD_BLOCKER)
        hard = True
    checked = (
        ("not_in_resume", outcome.resume),
        ("not_in_pack", f"{outcome.resume}\n{outcome.letter}"),
    )
    for key, documents in checked:
        for trap in expect.get(key, []):
            if _claims(documents, trap):
                failures.append(f"An Invented Claim reached the final Pack: “{trap}”")
                fixes.append(FIX_PACK)
                hard = True
    # A wrong removal is tracked, not a Hard Failure.
    for kept in expect.get("in_pack", []):
        if not _mentions(f"{outcome.resume}\n{outcome.letter}", kept):
            failures.append(f"A Claim the Evidence supports was removed: “{kept}”")
            fixes.append(FIX_VERIFY)
    # A Hard Failure's area comes first, since it matters most.
    return Verdict(failures, hard, FIX_PACK if FIX_PACK in fixes else next(iter(fixes), None))


class LabelsMetric(BaseMetric):  # type: ignore[no-untyped-call]
    """Pass when the outcome matches every label of the case; any Hard Failure is recorded."""

    def __init__(self) -> None:
        self.threshold = 1.0
        self.async_mode = False
        self.hard_failure = False
        self.fix_area: str | None = None

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        failures, self.hard_failure, self.fix_area = judge(
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


def _documents_text(pack: applications.WrittenPack) -> tuple[str, str]:
    lines = [claim.text for claim in pack.resume.all_claims()]
    letter = [s.text for p in pack.cover_letter.paragraphs for s in p]
    return "\n".join(lines), "\n".join(letter)


def run_case(case: dict[str, Any], profile: dict[str, Any]) -> Outcome:
    """Send one case through the real steps, as the invented eval person."""
    outcome = Outcome()
    posting = case["posting"]
    # A case labelled with a Filter result, an injection case included, stops at Filter.
    if "passes" in case["expect"]:
        decision = filter.decide(filter.read_facts(EVAL_USER, posting), profile["preferences"])
        outcome.passes, outcome.filter_reason = decision.passed, decision.reason
        return outcome
    evidence = dict(enumerate(profile["evidence"], start=1))
    match = rating.rate_posting(EVAL_USER, posting, evidence, profile["facts"])
    outcome.band, outcome.band_reasons = match.band, match.reasons + match.gaps
    # An unknown Hard Blocker only holds a Band back, so it doesn't count as caught.
    outcome.missing_hard_blockers = [
        r.requirement
        for r in match.requirements
        if r.kind == "hard_blocker" and r.result == "missing"
    ]
    # A case labelled with what a Pack may or must hold goes on to write one.
    if {"not_in_resume", "not_in_pack", "in_pack"} & case["expect"].keys():
        pack_evidence: dict[int, dict[str, Any]] = {
            n: {"text": text, "origin": "self_reported", "id": None} for n, text in evidence.items()
        }
        pack_evidence[applications.EDUCATION_EVIDENCE] = {
            "text": f"Education: {profile['facts']['education']}",
            "origin": "profile",
            "id": None,
        }
        requirements = [r.model_dump() for r in match.requirements]
        pack = applications.write_pack(EVAL_USER, posting, requirements, pack_evidence)
        outcome.resume, outcome.letter = _documents_text(pack)
    return outcome


def _result(case: dict[str, Any], profile: dict[str, Any]) -> tuple[Status, bool, str, str | None]:
    """Run and judge one case: its status, whether it's a Hard Failure, why, and where to look
    first to fix it."""
    try:
        outcome = run_case(case, profile)
    except gateway.CapReached:
        return "did_not_run", False, "Did not run: the eval budget is used up", None
    except gateway.ModelUnavailable as error:
        if any(kind in str(error) for kind in DID_NOT_RUN):
            return "did_not_run", False, f"Did not run: {error}", None
        return "failed", False, f"The model call failed: {error}", FIX_MODEL
    except ValueError as error:
        reason = f"The model's answer couldn't be used ({type(error).__name__})"
        return "failed", False, reason, FIX_ANSWER
    except Exception as error:
        # One case's crash fails only that case; the run goes on to the next.
        log.exception("Eval Case %s crashed", case["id"])
        return "failed", False, f"The case crashed ({type(error).__name__})", FIX_CRASH
    metric = LabelsMetric()
    metric.measure(
        LLMTestCase(
            input=case["posting"],
            expected_output=json.dumps(case["expect"]),
            metadata={"outcome": outcome},
        )
    )
    status: Status = "passed" if metric.success else "failed"
    return status, metric.hard_failure, str(metric.reason), metric.fix_area


def run(owner: UUID, cases_file: Path = CASES_FILE) -> int:
    """Run every case, store the results, and return the Eval Run's ID."""
    loaded = json.loads(cases_file.read_text(encoding="utf-8"))
    with connect() as conn:
        run_row: Any = conn.execute(
            """INSERT INTO eval_runs (user_id, deepeval_version) VALUES (%s, %s)
               RETURNING id, started_at""",
            (owner, version("deepeval")),
        ).fetchone()
    try:
        for case in loaded["cases"]:
            status, hard, reason, fix_area = _result(case, loaded["profile"])
            with connect() as conn:
                conn.execute(
                    """INSERT INTO eval_results (user_id, run_id, case_id, area, status,
                                                hard_failure, labels_checked, reason, fix_area)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        owner,
                        run_row["id"],
                        case["id"],
                        case["area"],
                        status,
                        hard,
                        case["labels_checked"],
                        reason,
                        fix_area,
                    ),
                )
    finally:
        # Even a run that stopped early is finished, so what it recorded shows and counts.
        with connect() as conn:
            conn.execute(
                # ponytail: a run's cost is all eval spending since it started, so two runs at
                # once would count each other's; tag model calls with their run if they overlap.
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
            """SELECT case_id, area, status, hard_failure, labels_checked, reason, fix_area
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
        fix = f" Look first at: {r['fix_area']}" if r["fix_area"] else ""
        lines.append(f"{r['case_id']:32} {r['area']:9} {result:12} {labels:10} {r['reason']}.{fix}")
    lines.append(f"Hard Failures: {hard}. Results of unchecked cases aren't trusted yet.")
    return "\n".join(lines)


def main() -> None:
    owner = current_user_id()
    if sys.argv[1:] != ["show"]:
        run(owner)
    print(table(owner))


if __name__ == "__main__":
    main()
