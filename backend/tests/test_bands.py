import random

import pytest

from job_copilot.bands import Judged, rate

MET = [Judged(f"Skill {n}", "must_have", "met") for n in range(3)]


def must(text: str, result: str) -> Judged:
    return Judged(text, "must_have", result)  # type: ignore[arg-type]


def test_all_must_haves_met_and_seniority_fitting_is_high() -> None:
    rating = rate(MET, "fits")

    assert rating.band == "High"
    assert rating.reasons[0] == "All must-haves are backed by Evidence"


def test_one_partial_must_have_still_allows_high() -> None:
    assert rate([*MET, must("Docker", "partial")], "fits").band == "High"


@pytest.mark.parametrize("result", ["missing", "unknown"])
def test_one_must_have_missing_or_unknown_is_medium_and_named_first(result: str) -> None:
    rating = rate([*MET, must("Kubernetes", result)], "fits")

    assert rating.band == "Medium"
    assert rating.reasons[0] == "Held back by one must-have: Kubernetes"
    assert "Kubernetes: no Evidence found" in rating.gaps


def test_two_partial_must_haves_are_medium() -> None:
    rating = rate([*MET, must("Docker", "partial"), must("Go", "partial")], "fits")

    assert rating.band == "Medium"
    assert rating.reasons[0] == "Held back by 2 Partial Requirements: Docker, Go"


@pytest.mark.parametrize(
    ("seniority", "reason"),
    [
        ("one_off", "Held back: seniority is one level off"),
        ("two_off", "Held back: seniority is two or more levels off"),
        ("unknown", "Held back: your seniority isn't in your Profile"),
    ],
)
def test_seniority_off_without_a_firm_minimum_is_medium(seniority: str, reason: str) -> None:
    rating = rate(MET, seniority)  # type: ignore[arg-type]

    assert (rating.band, rating.reasons[0]) == ("Medium", reason)


def test_fewer_than_three_clear_requirements_is_medium() -> None:
    rating = rate(MET[:2], "fits")

    assert rating.band == "Medium"
    assert rating.reasons[0] == "Held back: fewer than three clear Requirements"


def test_a_missing_hard_blocker_is_low_whatever_else_is_met() -> None:
    rating = rate([*MET, Judged("Security clearance", "hard_blocker", "missing")], "fits")

    assert rating.band == "Low"
    assert rating.reasons[0] == "Hard Blocker: Security clearance"


def test_an_unknown_hard_blocker_counts_as_one_unknown_must_have_not_a_blocker() -> None:
    rating = rate([*MET, Judged("Work authorization", "hard_blocker", "unknown")], "fits")

    assert rating.band == "Medium"


def test_two_must_haves_missing_or_unknown_are_low() -> None:
    rating = rate([*MET, must("Kubernetes", "missing"), must("Go", "unknown")], "fits")

    assert rating.band == "Low"
    assert rating.reasons[0] == "2 must-haves have no Evidence: Go, Kubernetes"


def test_seniority_below_a_firm_minimum_is_low() -> None:
    rating = rate(MET, "two_off_firm")

    assert (rating.band, rating.reasons[0]) == ("Low", "Below the posting's firm seniority minimum")


def test_low_rules_come_before_medium_rules() -> None:
    blocked = [*MET, must("Go", "missing"), Judged("Clearance", "hard_blocker", "missing")]

    assert rate(blocked, "one_off").band == "Low"


def test_nice_to_haves_never_change_the_band() -> None:
    missing_nice = [Judged(f"Nice {n}", "nice_to_have", "missing") for n in range(5)]
    met_nice = [Judged(f"Nice {n}", "nice_to_have", "met") for n in range(5)]

    assert rate([*MET, *missing_nice], "fits").band == "High"
    assert rate([*MET, must("Go", "missing"), *met_nice], "fits").band == "Medium"
    assert rate([*MET, *met_nice], "fits").nice_met == 5


def test_the_band_doesnt_depend_on_requirement_order() -> None:
    requirements = [*MET, must("Docker", "partial"), Judged("Nice", "nice_to_have", "missing")]
    shuffled = random.Random(7).sample(requirements, len(requirements))

    assert rate(shuffled, "fits") == rate(requirements, "fits")


def test_at_most_three_reasons() -> None:
    nice = [Judged("Nice", "nice_to_have", "met")]

    assert len(rate([*MET, *nice], "fits").reasons) <= 3
    assert rate([*MET, *nice], "fits").reasons == [
        "All must-haves are backed by Evidence",
        "Seniority fits",
        "1 nice-to-have met",
    ]
