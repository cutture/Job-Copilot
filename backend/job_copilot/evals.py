"""Eval Runs: invented Eval Cases through the real Filter, rating and Pack steps.

The worker runs every case once a day, after EVAL_HOUR_UTC, each case as its own job behind
the person's own work. The owner can also run them all at once by hand:

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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
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

from job_copilot import applications, bands, eval_runs, filter, gateway, rating  # noqa: E402
from job_copilot.db import EVAL_USER_ID, connect, current_user_id  # noqa: E402
from job_copilot.tracked_scores import (  # noqa: E402
    CaseScores,
    ExtractedRequirement,
    requirement_hits,
)

log = logging.getLogger(__name__)

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
    # Each extracted Requirement: its words, its quote and its Result.
    requirements: list[ExtractedRequirement] = field(default_factory=list)
    # The Band for the same posting with its sentences in reverse order.
    reordered_band: bands.Band | None = None
    resume: str = ""
    letter: str = ""
    # How many Claims the writer wrote, and each one Verification removed, with its kind.
    claims_written: int = 0
    removed_kinds: list[str] = field(default_factory=list)
    removed_texts: list[str] = field(default_factory=list)


class CaseResult(NamedTuple):
    status: Status
    hard_failure: bool
    reason: str
    fix_area: str | None
    scores: CaseScores | None = None


# The words that start a posting's list of asks, as in "You need A, B, and C."
ASKS = re.compile(r"^(.*?\b(?:need|needs|must have|requires?)\s)(.+?)\.?$")


def _reordered_asks(sentence: str) -> str:
    """A sentence listing asks, with them in reverse order; any other sentence as it is."""
    found = ASKS.match(sentence)
    asks = re.split(r",\s*(?:and\s+)?|\s+and\s+", found.group(2)) if found else []
    if not found or len(asks) < 2:
        return sentence
    asks.reverse()
    joined = ", ".join(asks[:-1]) + (", and " if len(asks) > 2 else " and ") + asks[-1]
    return f"{found.group(1)}{joined}."


def reordered(posting: str) -> str:
    """The posting with its asks, and its sentences after the first, in reverse order.

    ponytail: finds asks only in sentences like "You need A, B, and C."; a bulleted list or
    other wording keeps its order. Split bullets too if real postings get added as cases.
    """
    first, *rest = re.split(r"(?<=\.) ", posting)
    return " ".join([first, *(_reordered_asks(s) for s in reversed(rest))])


def _pack_text(outcome: Outcome) -> str:
    return f"{outcome.resume}\n{outcome.letter}"


def _planted_traps(expect: dict[str, Any], outcome: Outcome) -> list[tuple[str, str]]:
    """Each Trap planted in a case, with the documents it must stay out of."""
    documents = {"not_in_resume": outcome.resume, "not_in_pack": _pack_text(outcome)}
    return [(trap, text) for key, text in documents.items() for trap in expect.get(key, [])]


def case_scores(expect: dict[str, Any], outcome: Outcome) -> CaseScores:
    """What one case counts towards its run's Tracked Scores."""
    right, labelled = requirement_hits(expect.get("requirements", {}), outcome.requirements)
    supported = expect.get("in_pack", [])
    # Verification's own catches: of the Traps the writer wrote, those it removed.
    removed = [
        trap
        for trap, _ in _planted_traps(expect, outcome)
        if any(_mentions(text, trap) for text in outcome.removed_texts)
    ]
    leaked = [trap for trap, text in _planted_traps(expect, outcome) if _claims(text, trap)]
    return CaseScores(
        band_exact=outcome.band == expect["band"] if "band" in expect else None,
        requirements_right=right,
        requirements_labelled=labelled,
        # A supported Claim Verification removed; one the writer never wrote isn't a removal.
        wrongly_removed=sum(
            any(_mentions(text, phrase) for text in outcome.removed_texts) for phrase in supported
        ),
        supported_labelled=len(supported),
        claims_written=outcome.claims_written,
        stretched=outcome.removed_kinds.count("stretched"),
        invented=outcome.removed_kinds.count("invented"),
        same_band_reordered=(
            outcome.reordered_band == outcome.band if outcome.reordered_band else None
        ),
        traps_caught=len([trap for trap in removed if trap not in leaked]),
        traps_written=len(set(removed) | set(leaked)),
    )


def _mentions(text: str, phrase: str) -> bool:
    """A whole-word match, so "Rust" doesn't match "trust"."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE) is not None


class Verdict(NamedTuple):
    """What failed, whether any of it is a Hard Failure, and where to look first to fix it."""

    failures: list[str]
    hard: bool
    fix_area: str | None


# Wording that says what the posting asks for, which claims nothing about the person.
POSTING_ASKS = re.compile(
    r"\b(?:asks? for|asking for|requires?|required|calls for|(?:is|are|you're) looking for|"
    r"seeks|seeking|wants)\b",
    re.IGNORECASE,
)
# The person speaking about applying or writing, which claims nothing they have.
APPLYING = re.compile(
    r"\b(?:I am|I'm|I)\s+(?:applying|writing|apply|write)\b|\bI(?:'d| would) like to apply\b",
    re.IGNORECASE,
)
# Any other first-person words, which can carry a claim even beside what the posting asks for.
FIRST_PERSON = re.compile(r"\b(?:I|I'm|I've|I'd|me|my|mine)\b", re.IGNORECASE)


def _only_about_the_posting(line: str) -> bool:
    """Whether a line only says what the posting asks for: about the person, it says at most
    that they're applying or writing."""
    return bool(POSTING_ASKS.search(line)) and not FIRST_PERSON.search(APPLYING.sub(" ", line))


def _claims(documents: str, trap: str) -> bool:
    """Whether a line of the documents claims the trap, rather than saying it's lacking or
    only what the posting asks for."""
    return any(
        _mentions(line, trap) and not NEGATION.search(line) and not _only_about_the_posting(line)
        for line in documents.splitlines()
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
    for trap, documents in _planted_traps(expect, outcome):
        if _claims(documents, trap):
            failures.append(f"An Invented Claim reached the final Pack: “{trap}”")
            fixes.append(FIX_PACK)
            hard = True
    # A wrong removal is tracked, not a Hard Failure.
    for kept in expect.get("in_pack", []):
        if not _mentions(_pack_text(outcome), kept):
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
        decision = filter.decide(filter.read_facts(EVAL_USER_ID, posting), profile["preferences"])
        outcome.passes, outcome.filter_reason = decision.passed, decision.reason
        return outcome
    evidence = dict(enumerate(profile["evidence"], start=1))
    match = rating.rate_posting(EVAL_USER_ID, posting, evidence, profile["facts"])
    outcome.band, outcome.band_reasons = match.band, match.reasons + match.gaps
    # An unknown Hard Blocker only holds a Band back, so it doesn't count as caught.
    outcome.missing_hard_blockers = [
        r.requirement
        for r in match.requirements
        if r.kind == "hard_blocker" and r.result == "missing"
    ]
    outcome.requirements = [
        ExtractedRequirement(r.requirement, r.quote, r.result) for r in match.requirements
    ]
    if case["area"] == "scoring":
        # Report only: the Band shouldn't depend on the order a posting lists its asks in.
        try:
            again = rating.rate_posting(
                EVAL_USER_ID, reordered(posting), evidence, profile["facts"]
            )
            outcome.reordered_band = again.band
        except Exception as error:
            # A report-only check never changes the case's own result.
            log.warning("Reordered rating failed: %s", type(error).__name__)
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
        pack = applications.write_pack(EVAL_USER_ID, posting, requirements, pack_evidence)
        outcome.resume, outcome.letter = _documents_text(pack)
        outcome.removed_kinds = [claim.kind for claim in pack.removed]
        outcome.removed_texts = [claim.text for claim in pack.removed]
        kept = len(pack.resume.all_claims()) + sum(map(len, pack.cover_letter.paragraphs))
        outcome.claims_written = kept + len(pack.removed)
    return outcome


def _result(case: dict[str, Any], profile: dict[str, Any]) -> CaseResult:
    """Run and judge one case: its status, whether it's a Hard Failure, why, where to look
    first to fix it, and what it counts towards the run's Tracked Scores."""
    try:
        outcome = run_case(case, profile)
    except gateway.CapReached:
        return CaseResult("did_not_run", False, "Did not run: the eval budget is used up", None)
    except gateway.ModelUnavailable as error:
        if any(kind in str(error) for kind in DID_NOT_RUN):
            return CaseResult("did_not_run", False, f"Did not run: {error}", None)
        return CaseResult("failed", False, f"The model call failed: {error}", FIX_MODEL)
    except ValueError as error:
        reason = f"The model's answer couldn't be used ({type(error).__name__})"
        return CaseResult("failed", False, reason, FIX_ANSWER)
    except Exception as error:
        # One case's crash fails only that case; the run goes on to the next.
        log.exception("Eval Case %s crashed", case["id"])
        return CaseResult("failed", False, f"The case crashed ({type(error).__name__})", FIX_CRASH)
    metric = LabelsMetric()
    metric.measure(
        LLMTestCase(
            input=case["posting"],
            expected_output=json.dumps(case["expect"]),
            metadata={"outcome": outcome},
        )
    )
    status: Status = "passed" if metric.success else "failed"
    return CaseResult(
        status,
        metric.hard_failure,
        str(metric.reason),
        metric.fix_area,
        case_scores(case["expect"], outcome),
    )


def _record(owner: UUID, run_id: int, case: dict[str, Any], profile: dict[str, Any]) -> None:
    case = eval_runs.for_challenger(case, gateway.active_challenger())
    with gateway.recording_models() as used:
        result = _result(case, profile)
    eval_runs.record_result(owner, run_id, case, *result, models=used)


@contextmanager
def _running_as(challenger: eval_runs.Challenger | None) -> Iterator[None]:
    """Run as a Challenger run, or on the person's own models."""
    if challenger is None:
        yield
        return
    with gateway.challenging(challenger):
        yield


def run_queued_case(
    owner: UUID, run_id: int, case_id: str, cases_file: Path = eval_runs.CASES_FILE
) -> None:
    """Run one queued case of a run, and finish the run after its last case."""
    loaded = eval_runs.load_cases(cases_file)
    # A case removed from the file since the run was queued is skipped.
    with _running_as(eval_runs.challenger_of(owner, run_id)):
        for case in loaded["cases"]:
            if case["id"] == case_id:
                _record(owner, run_id, case, loaded["profile"])
    eval_runs.finish_runs(owner, run_id)


def run(
    owner: UUID,
    cases_file: Path = eval_runs.CASES_FILE,
    challenger: eval_runs.Challenger | None = None,
) -> int:
    """Run every case now, or a Challenger's on the cases that use its step, store the
    results, and return the Eval Run's ID."""
    loaded = eval_runs.load_cases(cases_file)
    cases = [
        c for c in loaded["cases"] if not challenger or eval_runs.uses_step(c, challenger.step)
    ]
    with connect() as conn:
        run_id = int(eval_runs.start_run(conn, owner, challenger)["id"])
    try:
        with _running_as(challenger):
            for case in cases:
                _record(owner, run_id, case, loaded["profile"])
    finally:
        # Even a run that stopped early is finished, so what it recorded shows and counts.
        eval_runs.finish_runs(owner, run_id)
    return run_id


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
    """`show` prints the latest run; `challenger <step> <model>` runs a Challenger, such as
    `challenger rating anthropic/claude-sonnet-5-5`; nothing else runs every case now."""
    owner = current_user_id()
    match sys.argv[1:]:
        case ["show"]:
            pass
        case ["challenger", step, model] if step in eval_runs.CHALLENGER_STEPS and (
            gateway.DataClass.PERSONAL in getattr(gateway.MODELS.get(model), "data_classes", ())
        ):
            run(owner, challenger=gateway.Challenger(step, model))
        case []:
            run(owner)
        case _:
            sys.exit(main.__doc__)
    print(table(owner))


if __name__ == "__main__":
    main()
