"""Tracked Scores: how well each step does across a run, beside its Hard Failures.

Each case stores what it counted; a run's score adds those up over cases whose labels the owner
has checked. A missed target shows on the Eval Runs page but never turns on the red banner.
"""

import re
from collections.abc import Callable, Sequence
from typing import Any, NamedTuple

from pydantic import BaseModel

REPORT_ONLY = "Report only"


class CaseScores(BaseModel):
    """What one case counted towards the run's scores. Empty for steps the case skips."""

    band_exact: bool | None = None
    requirements_right: int = 0
    requirements_labelled: int = 0
    # Of the Claims labelled as supported, how many Verification removed.
    wrongly_removed: int = 0
    supported_labelled: int = 0
    claims_written: int = 0
    stretched: int = 0
    invented: int = 0
    same_band_reordered: bool | None = None
    # Of the Traps the writer wrote, how many Verification removed.
    traps_caught: int = 0
    traps_written: int = 0


class TrackedScore(BaseModel):
    name: str
    # A percentage, or None when no checked case counted towards it.
    value: int | None
    target: str
    # None for a report-only score, or one with nothing to count.
    met: bool | None


class ExtractedRequirement(NamedTuple):
    requirement: str
    quote: str | None
    result: str


def requirement_hits(
    labels: dict[str, str], extracted: Sequence[ExtractedRequirement]
) -> tuple[int, int]:
    """How many labelled Requirements were extracted with the labelled Result, out of all.

    A label names a phrase from the posting; a Requirement matches when its own words or its
    quote contain that phrase as whole words. A label no Requirement matches counts as wrong.
    """
    right = 0
    for phrase, expected in labels.items():
        whole = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
        results = [
            found.result
            for found in extracted
            if whole.search(found.requirement) or whole.search(found.quote or "")
        ]
        right += expected in results
    return right, len(labels)


def _percent(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def scores_for(results: Sequence[dict[str, Any]]) -> list[TrackedScore]:
    """A run's Tracked Scores from its case results, each a dict with `scores`,
    `labels_checked` and `scores_checked`."""
    trusted = [r["scores"] for r in results if r["labels_checked"]]
    # Labels added for Tracked Scores count once the owner has checked them too.
    score_labels_checked = [
        r["scores"] for r in results if r["labels_checked"] and r["scores_checked"]
    ]

    def total(cases: list[CaseScores], field: Callable[[CaseScores], int]) -> int:
        return sum(field(c) for c in cases)

    banded = [c.band_exact for c in trusted if c.band_exact is not None]
    reordered = [c.same_band_reordered for c in trusted if c.same_band_reordered is not None]
    written = total(trusted, lambda c: c.claims_written)
    supported = total(trusted, lambda c: c.supported_labelled)

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
                total(score_labels_checked, lambda c: c.requirements_right),
                total(score_labels_checked, lambda c: c.requirements_labelled),
            ),
            85,
            at_least=True,
        ),
        judged(
            "Wrong removals",
            _percent(total(trusted, lambda c: c.wrongly_removed), supported),
            10,
            at_least=False,
        ),
        reported("Stretched Claims", _percent(total(trusted, lambda c: c.stretched), written)),
        reported("Writer invention rate", _percent(total(trusted, lambda c: c.invented), written)),
        reported(
            "Same Band after reordering Requirements", _percent(sum(reordered), len(reordered))
        ),
        reported(
            "Traps caught",
            _percent(
                total(trusted, lambda c: c.traps_caught),
                total(trusted, lambda c: c.traps_written),
            ),
        ),
    ]
