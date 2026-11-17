"""Tracked Scores: direct tests of each calculation, and the Eval Runs page that shows them."""

import json
from pathlib import Path
from typing import Any

import psycopg
from fastapi.testclient import TestClient

from job_copilot import eval_runs, evals, gateway, rating
from job_copilot.tracked_scores import (
    CaseScores,
    ExtractedRequirement,
    requirement_hits,
    scores_for,
)
from tests.conftest import TEST_DB, FakeProvider
from tests.test_evals import OWNER, cases_file
from tests.test_rating import answer, requirement

# The extracted Requirements of one rating.
EXTRACTED = [
    ExtractedRequirement("3+ years of Python", "You need 3+ years of Python", "met"),
    ExtractedRequirement(
        "Kubernetes in production", "experience running Kubernetes in production", "missing"
    ),
    ExtractedRequirement(
        "Retrieval-augmented systems", "building retrieval-augmented systems", "partial"
    ),
]


def checked(scores: CaseScores, labels: bool = True, scores_checked: bool = True) -> dict[str, Any]:
    return {"scores": scores, "labels_checked": labels, "scores_checked": scores_checked}


def by_name(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {s.name: s for s in scores_for(results)}


def test_a_requirement_label_counts_when_a_requirement_names_its_phrase_with_that_result() -> None:
    labels = {"Python": "met", "Kubernetes": "missing", "retrieval-augmented": "met"}

    assert requirement_hits(labels, EXTRACTED) == (2, 3)


def test_a_label_no_extracted_requirement_names_counts_as_wrong() -> None:
    assert requirement_hits({"Rust": "missing"}, EXTRACTED) == (0, 1)


def test_a_label_matches_whole_words_only() -> None:
    extracted = [ExtractedRequirement("MicroPython firmware", "MicroPython firmware", "missing")]

    assert requirement_hits({"Python": "missing"}, extracted) == (0, 1)


def test_exact_band_is_the_share_of_checked_band_cases_rated_right() -> None:
    results = [
        checked(CaseScores(band_exact=True)),
        checked(CaseScores(band_exact=True)),
        checked(CaseScores(band_exact=True)),
        checked(CaseScores(band_exact=True)),
        checked(CaseScores(band_exact=False)),
        # Unchecked labels don't count.
        checked(CaseScores(band_exact=False), labels=False),
    ]

    band = by_name(results)["Exact Band"]
    assert (band.value, band.target, band.met) == (80, "80% or more", True)


def test_requirement_results_count_only_cases_whose_new_labels_are_checked() -> None:
    results = [
        checked(CaseScores(requirements_right=17, requirements_labelled=20)),
        checked(CaseScores(requirements_right=0, requirements_labelled=5), scores_checked=False),
    ]

    score = by_name(results)["Requirement Results"]
    assert (score.value, score.met) == (85, True)


def test_wrong_removals_is_the_share_of_supported_claims_removed() -> None:
    results = [checked(CaseScores(wrongly_removed=2, supported_labelled=10))]

    score = by_name(results)["Wrong removals"]
    assert (score.value, score.target, score.met) == (20, "10% or less", False)


def test_stretched_claims_and_invention_are_shares_of_what_the_writer_wrote_and_report_only() -> (
    None
):
    results = [
        checked(CaseScores(claims_written=40, stretched=2, invented=1)),
        checked(CaseScores(claims_written=10, stretched=0, invented=0)),
    ]

    scores = by_name(results)
    assert (scores["Stretched Claims"].value, scores["Stretched Claims"].met) == (4, None)
    assert (scores["Writer invention rate"].value, scores["Writer invention rate"].met) == (2, None)


def test_same_band_after_reordering_is_report_only() -> None:
    results = [
        checked(CaseScores(same_band_reordered=True)),
        checked(CaseScores(same_band_reordered=False)),
    ]

    score = by_name(results)["Same Band after reordering Requirements"]
    assert (score.value, score.target, score.met) == (50, "Report only", None)


def test_same_band_after_rescore_is_report_only() -> None:
    results = [
        checked(CaseScores(same_band_rescored=True)),
        checked(CaseScores(same_band_rescored=True)),
        checked(CaseScores(same_band_rescored=False)),
        checked(CaseScores(same_band_rescored=True)),
    ]

    score = by_name(results)["Same Band after Rescore"]
    assert (score.value, score.target, score.met) == (75, "Report only", None)


def test_a_score_with_nothing_to_count_has_no_value_and_isnt_judged() -> None:
    score = by_name([])["Exact Band"]

    assert (score.value, score.met) == (None, None)


def test_every_scoring_case_has_requirement_labels_waiting_for_the_owners_check() -> None:
    for case in eval_runs.load_cases()["cases"]:
        if case["area"] == "scoring":
            assert case["expect"]["requirements"], case["id"]
            assert set(case["expect"]["requirements"].values()) <= {"met", "partial", "missing"}
            assert "scores_checked" in case


def test_a_run_shows_its_tracked_scores_and_new_labels_wait_for_the_owners_check(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    # Python is extracted as met, as its one Requirement label expects.
    provider.answers = {
        rating.RATING_MODEL: json.dumps(
            answer(
                requirement("Python", "Python developer", evidence=[1]),
                seniority={"level": None, "quote": None},
            )
        )
    }

    path = cases_file(tmp_path, "scoring-thin-posting")
    unchecked = json.loads(path.read_text(encoding="utf-8"))
    unchecked["cases"][0]["scores_checked"] = False
    path.write_text(json.dumps(unchecked), encoding="utf-8")

    run_id = evals.run(OWNER, path)

    scores = {s["name"]: s for s in client.get(f"/api/eval-runs/{run_id}").json()["tracked_scores"]}
    assert scores["Same Band after reordering Requirements"]["value"] == 100
    # The new Requirement labels aren't checked yet, so they don't count.
    assert scores["Requirement Results"]["value"] is None

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE eval_results SET scores_checked = true")
    scores = {s["name"]: s for s in client.get(f"/api/eval-runs/{run_id}").json()["tracked_scores"]}
    assert (scores["Requirement Results"]["value"], scores["Requirement Results"]["met"]) == (
        100,
        True,
    )


def test_reordering_reverses_the_asks_and_the_sentences_after_the_first() -> None:
    posting = (
        "AI Engineer at Example Labs. You need 3+ years of Python, experience building "
        "retrieval-augmented systems, and experience evaluating LLM output. Apply at "
        "careers@example.com."
    )

    assert evals.reordered(posting) == (
        "AI Engineer at Example Labs. Apply at careers@example.com. You need experience "
        "evaluating LLM output, experience building retrieval-augmented systems, and 3+ years "
        "of Python."
    )


def test_a_failed_reordering_leaves_the_cases_own_result_alone(
    client: TestClient, provider: FakeProvider, tmp_path: Path, monkeypatch: Any
) -> None:
    provider.answers = {
        rating.RATING_MODEL: json.dumps(
            answer(
                requirement("Python", "Python developer", evidence=[1]),
                seniority={"level": None, "quote": None},
            )
        )
    }
    rate = rating.rate_posting
    calls = iter([None, gateway.ModelUnavailable("down")])

    def second_call_fails(*args: Any) -> Any:
        error = next(calls)
        if error:
            raise error
        return rate(*args)

    monkeypatch.setattr(rating, "rate_posting", second_call_fails)

    run_id = evals.run(OWNER, cases_file(tmp_path, "scoring-thin-posting"))

    run = client.get(f"/api/eval-runs/{run_id}").json()
    assert run["results"][0]["status"] == "passed"
    scores = {s["name"]: s for s in run["tracked_scores"]}
    assert scores["Exact Band"]["value"] == 100
    assert scores["Same Band after reordering Requirements"]["value"] is None


def test_wrong_removals_count_only_supported_claims_verification_removed() -> None:
    outcome = evals.Outcome(
        resume="Wrote evaluation suites with DeepEval",
        removed_texts=["Cut latency by 30% across every service"],
    )

    scores = evals.case_scores({"in_pack": ["DeepEval", "30%", "Postgres"]}, outcome)

    # Postgres was never written, which isn't a removal.
    assert (scores.wrongly_removed, scores.supported_labelled) == (1, 3)


def test_traps_caught_is_the_share_of_written_traps_verification_removed() -> None:
    # The writer wrote three traps: Verification removed Kubernetes and Rust, and missed PhD.
    # Terraform was never written, so it says nothing about Verification.
    outcome = evals.Outcome(
        resume="Python\nI hold a PhD in Physics",
        letter="I build in Python.",
        removed_texts=["Kubernetes", "Ran Rust services"],
    )

    scores = evals.case_scores(
        {"not_in_pack": ["PhD", "Kubernetes", "Terraform"], "not_in_resume": ["Rust"]}, outcome
    )

    assert (scores.traps_caught, scores.traps_written) == (2, 3)
    score = by_name([checked(scores)])["Traps caught"]
    assert (score.value, score.target, score.met) == (67, "Report only", None)


def test_a_case_whose_writer_wrote_no_trap_gives_traps_caught_nothing_to_count() -> None:
    scores = evals.case_scores({"not_in_pack": ["PhD"]}, evals.Outcome(resume="Python"))

    assert by_name([checked(scores)])["Traps caught"].value is None
