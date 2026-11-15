"""Tracked Scores: how well each step does across a run, beside its Hard Failures.

Each case stores what it counted; a run's score adds those up over cases whose labels the owner
has checked. A missed target shows on the Eval Runs page but never turns on the red banner.
"""

from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel

REPORT_ONLY = "Report only"


class CaseScores(BaseModel):
    """What one case counted towards the run's scores. Empty for steps the case skips."""

    band_exact: bool | None = None
    requirements_right: int = 0
    requirements_labelled: int = 0
    kept_right: int = 0
    kept_labelled: int = 0
    claims_written: int = 0
    stretched: int = 0
    invented: int = 0
    same_band_reordered: bool | None = None


class TrackedScore(BaseModel):
    name: str
    # A percentage, or None when no checked case counted towards it.
    value: int | None
    target: str
    # None for a report-only score, or one with nothing to count.
    met: bool | None


def requirement_hits(
    labels: dict[str, str], extracted: Sequence[tuple[str, str | None, str]]
) -> tuple[int, int]:
    """How many labelled Requirements were extracted with the labelled Result, out of all.

    A label names a phrase from the posting; a Requirement matches when its own words or its
    quote contain that phrase. A label no Requirement matches counts as wrong.
    """
    right = 0
    for phrase, expected in labels.items():
        wanted = phrase.lower()
        results = [
            result
            for requirement, quote, result in extracted
            if wanted in requirement.lower() or wanted in (quote or "").lower()
        ]
        right += expected in results
    return right, len(labels)


def _percent(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def scores_for(results: Sequence[dict[str, Any]]) -> list[TrackedScore]:
    """A run's Tracked Scores from its case results, each a dict with `scores`,
    `labels_checked` and `scores_checked`."""
    trusted = [r["scores"] for r in results if r["labels_checked"]]
    newly_labelled = [r["scores"] for r in results if r["labels_checked"] and r["scores_checked"]]

    def total(cases: list[CaseScores], field: Callable[[CaseScores], int]) -> int:
        return sum(field(c) for c in cases)

    banded = [c.band_exact for c in trusted if c.band_exact is not None]
    reordered = [c.same_band_reordered for c in trusted if c.same_band_reordered is not None]
    written = total(trusted, lambda c: c.claims_written)
    kept_labelled = total(trusted, lambda c: c.kept_labelled)

    def judged(name: str, value: int | None, target: int, at_least: bool) -> TrackedScore:
        met = None if value is None else (value >= target if at_least else value <= target)
        wording = "or more" if at_least else "or less"
        return TrackedScore(name=name, value=value, target=f"{target}% {wording}", met=met)

    def reported(name: str, value: int | None) -> TrackedScore:
        return TrackedScore(name=name, value=value, target=REPORT_ONLY, met=None)

    return [
        judged("Exact Band", _percent(sum(banded), len(banded)), 80, at_least=True),
        judged(
            "Requirement Results",
            _percent(
                total(newly_labelled, lambda c: c.requirements_right),
                total(newly_labelled, lambda c: c.requirements_labelled),
            ),
            85,
            at_least=True,
        ),
        judged(
            "Wrong removals",
            _percent(kept_labelled - total(trusted, lambda c: c.kept_right), kept_labelled),
            10,
            at_least=False,
        ),
        reported("Stretched Claims", _percent(total(trusted, lambda c: c.stretched), written)),
        reported("Writer invention rate", _percent(total(trusted, lambda c: c.invented), written)),
        reported(
            "Same Band after reordering Requirements", _percent(sum(reordered), len(reordered))
        ),
    ]
