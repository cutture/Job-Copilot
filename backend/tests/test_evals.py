"""Eval Runs, with the model providers faked: the cases, the judging, and how results are kept."""

import json
import os
import re
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import eval_runs, evals, rating
from job_copilot.db import EVAL_USER_ID, SEEDED_USER_ID
from job_copilot.filter import FILTER_MODEL
from tests.conftest import TEST_DB, FakeProvider
from tests.test_filter import facts
from tests.test_rating import answer, requirement

OWNER = SEEDED_USER_ID
LOADED = eval_runs.load_cases()
CASES = {case["id"]: case for case in LOADED["cases"]}


def cases_file(tmp_path: Path, *ids: str, unchecked: tuple[str, ...] = ()) -> Path:
    """A cases file with these cases; any named in `unchecked` have labels not yet checked."""
    cases = [
        {**CASES[i], "labels_checked": CASES[i]["labels_checked"] and i not in unchecked}
        for i in ids
    ]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({**LOADED, "cases": cases}), encoding="utf-8")
    return path


def results() -> list[dict[str, Any]]:
    with psycopg.connect(TEST_DB) as conn:
        rows = conn.execute(
            "SELECT case_id, status, hard_failure, labels_checked, reason FROM eval_results "
            "ORDER BY id"
        ).fetchall()
    keys = ("case_id", "status", "hard_failure", "labels_checked", "reason")
    return [dict(zip(keys, row, strict=True)) for row in rows]


def test_the_cases_use_invented_data_and_keep_whether_their_labels_are_checked() -> None:
    text = json.dumps(LOADED)
    assert {d.rstrip(".") for d in re.findall(r"@([\w.-]+)", text)} == {"example.com"}
    # The owner checks every case's labels before its results are trusted.
    assert all(isinstance(case["labels_checked"], bool) for case in LOADED["cases"])


def test_a_run_reports_results_and_hard_failures(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    provider.answers = {
        FILTER_MODEL: facts(work_arrangement="on_site", locations=["Berlin, Germany"]),
        # The rating misses the Hard Blocker, and the writer plants a skill no Evidence has.
        rating.RATING_MODEL: json.dumps(
            answer(
                requirement("Python", "3+ years of Python", evidence=[1]),
                seniority={"level": None, "quote": None},
            )
        ),
    }
    resume = {
        "skills": [{"text": "Kubernetes", "evidence": [1]}],
        "experience": [],
        "education": [],
    }
    provider.tasks = {
        "resume": json.dumps(resume),
        "cover_letter": json.dumps(
            {"paragraphs": [{"sentences": [{"text": "Hello.", "evidence": []}]}]}
        ),
        "verify": json.dumps(
            {
                "statements": [
                    {"id": "s0", "verdict": "reworded", "evidence": [1]},
                    {"id": "c0s0", "verdict": "not_a_claim", "evidence": []},
                ]
            }
        ),
    }

    run_id = evals.run(
        OWNER,
        cases_file(
            tmp_path,
            "filter-on-site-elsewhere",
            "scoring-hard-blocker",
            "pack-trap-missing-skills",
            unchecked=("pack-trap-missing-skills",),
        ),
    )

    by_case = {r["case_id"]: r for r in results()}
    assert by_case["filter-on-site-elsewhere"]["status"] == "passed"
    blocker = by_case["scoring-hard-blocker"]
    assert (blocker["status"], blocker["hard_failure"]) == ("failed", True)
    assert "Missed the Hard Blocker" in blocker["reason"]
    trap = by_case["pack-trap-missing-skills"]
    assert (trap["status"], trap["hard_failure"]) == ("failed", True)
    assert trap["reason"] == "An Invented Claim reached the final Pack: “Kubernetes”"
    # Each result keeps whether its case's labels were checked when it ran.
    assert {case: r["labels_checked"] for case, r in by_case.items()} == {
        "filter-on-site-elsewhere": True,
        "scoring-hard-blocker": True,
        "pack-trap-missing-skills": False,
    }

    shown = evals.table(OWNER, run_id)
    assert "HARD FAIL" in shown and "unchecked" in shown and "Hard Failures: 2." in shown


def test_a_timeout_or_rate_limit_is_did_not_run_not_a_failure(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    provider.error = TimeoutError("timed out")

    evals.run(OWNER, cases_file(tmp_path, "scoring-strong-match"))

    [result] = results()
    assert (result["status"], result["hard_failure"]) == ("did_not_run", False)
    assert result["reason"].startswith("Did not run:")


def test_any_other_provider_error_fails_the_case_and_names_the_error(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    provider.error = PermissionError("bad key")

    evals.run(OWNER, cases_file(tmp_path, "scoring-strong-match"))

    [result] = results()
    assert result["status"] == "failed"
    assert (
        result["reason"].startswith("The model call failed:")
        and "PermissionError" in result["reason"]
    )


def test_traps_match_whole_words_and_wrong_bands_show_the_ratings_reasons() -> None:
    honest = evals.Outcome(resume="Built trust with support teams", letter="I'm a team leader")

    assert evals.judge({"not_in_resume": ["Rust"], "not_in_pack": ["team lead"]}, honest) == (
        [],
        False,
        None,
    )
    planted = evals.Outcome(resume="Rust, Python")
    assert evals.judge({"not_in_resume": ["Rust"]}, planted) == (
        ["An Invented Claim reached the final Pack: “Rust”"],
        True,
        evals.FIX_PACK,
    )
    medium = evals.Outcome(band="Medium", band_reasons=["Held back by one must-have: Python"])
    assert evals.judge({"band": "High"}, medium) == (
        ["Band was Medium, labelled High (Held back by one must-have: Python)"],
        False,
        evals.FIX_BAND,
    )
    assert evals.judge({"band": "High"}, evals.Outcome(band="Low"))[1] is True


def test_a_sentence_saying_a_trap_is_lacking_isnt_an_invented_claim() -> None:
    honest = evals.Outcome(letter="I don't hold the AWS Certified title yet.\nI build in Python.")
    claimed = evals.Outcome(letter="I am AWS Certified.")

    assert evals.judge({"not_in_pack": ["AWS Certified"]}, honest).failures == []
    assert evals.judge({"not_in_pack": ["AWS Certified"]}, claimed).hard is True


@pytest.mark.parametrize(
    ("line", "invented"),
    [
        # Saying what the posting asks for claims nothing about the person.
        (
            "I am applying for the AI Engineer role at Example Labs, which asks for at least "
            "five years of Python.",
            False,
        ),
        ("You're looking for five years of Python.", False),
        # Unless the line also says the person has it.
        ("I meet the five years of Python the role requires.", True),
        ("I bring the five years of Python you're looking for.", True),
        ("I have five years of Python.", True),
        # Code can't tell "and I build in Python" from "and I have it", so any other words about
        # the person count: a false alarm is safer than a missed Invented Claim.
        ("The role requires five years of Python, and I build in Python daily.", True),
        ("Your posting asks for five years of Python, which I earned at Example Co.", True),
        ("The role requires five years of Python and I am at five years of Python.", True),
        ("I'm writing because the role asks for five years of Python.", False),
    ],
)
def test_a_line_saying_what_the_posting_asks_for_isnt_an_invented_claim(
    line: str, invented: bool
) -> None:
    verdict = evals.judge({"not_in_pack": ["five years"]}, evals.Outcome(letter=line))

    assert verdict.hard is invented


def test_a_removed_supported_claim_is_a_failure_but_not_a_hard_one() -> None:
    verdict = evals.judge(
        {"in_pack": ["DeepEval", "30%"]}, evals.Outcome(resume="Cut latency by 30%")
    )

    assert verdict == (
        ["A Claim the Evidence supports was removed: “DeepEval”"],
        False,
        evals.FIX_VERIFY,
    )


def test_evals_stop_at_their_own_3_dollar_cap_and_leave_the_owners_ledger_alone(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    provider.answers = {rating.RATING_MODEL: json.dumps(answer())}
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        cap = conn.execute(
            "SELECT monthly_cap_usd FROM users WHERE id = %s", (EVAL_USER_ID,)
        ).fetchone()
        assert cap is not None and cap[0] == 3
        conn.execute("UPDATE users SET monthly_cap_usd = 0 WHERE id = %s", (EVAL_USER_ID,))
    try:
        evals.run(OWNER, cases_file(tmp_path, "scoring-strong-match"))
    finally:
        with psycopg.connect(TEST_DB, autocommit=True) as conn:
            conn.execute("UPDATE users SET monthly_cap_usd = 3 WHERE id = %s", (EVAL_USER_ID,))

    [result] = results()
    assert result["status"] == "did_not_run"
    with psycopg.connect(TEST_DB) as conn:
        owners = conn.execute("SELECT count(*) FROM model_calls WHERE user_id = %s", (OWNER,))
        assert owners.fetchone() == (0,)


def test_deepeval_sends_nothing_anywhere() -> None:
    assert os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] == "1"
    assert os.environ["CONFIDENT_TRACING_ENABLED"] == "NO"
    assert os.environ["DEEPEVAL_DISABLE_DOTENV"] == "1"
    assert "CONFIDENT_API_KEY" not in os.environ


def test_the_deepeval_version_is_pinned() -> None:
    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")

    assert re.search(r'"deepeval==\d+\.\d+\.\d+"', pyproject)


def test_eval_runs_stay_after_delete_everything_unless_the_box_is_ticked(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    provider.error = TimeoutError("timed out")
    evals.run(OWNER, cases_file(tmp_path, "scoring-strong-match"))

    client.post("/api/delete-everything", json={"confirm": "DELETE"})
    assert len(results()) == 1

    report = client.post(
        "/api/delete-everything", json={"confirm": "DELETE", "include_eval_runs": True}
    ).json()
    assert results() == []
    assert report["deleted"]["Eval Runs"] == 1


def test_the_change_request_trap_asks_the_writer_but_never_verification(
    provider: FakeProvider, tmp_path: Path
) -> None:
    [request] = CASES["pack-trap-change-request"]["change_requests"]
    provider.answers = {
        rating.RATING_MODEL: json.dumps(
            answer(requirement("Python", "3+ years of Python", evidence=[1]))
        ),
    }
    provider.tasks = {
        "resume": json.dumps({"skills": [{"text": "Python", "evidence": [1]}]}),
        "cover_letter": json.dumps(
            {"paragraphs": [{"sentences": [{"text": "Hello.", "evidence": []}]}]}
        ),
        "verify": json.dumps(
            {
                "statements": [
                    {"id": "s0", "verdict": "reworded", "evidence": [1]},
                    {"id": "c0s0", "verdict": "not_a_claim", "evidence": []},
                ]
            }
        ),
    }

    evals.run(OWNER, cases_file(tmp_path, "pack-trap-change-request"))

    written = [
        json.loads(r["messages"][-1]["content"])
        for r in provider.received
        if '"task": "resume"' in r["messages"][-1]["content"]
    ]
    assert written and written[0]["change_requests"] == [request]
    verifying = [r for r in provider.received if '"task": "verify"' in r["messages"][-1]["content"]]
    assert not any(request in m["content"] for r in verifying for m in r["messages"])
