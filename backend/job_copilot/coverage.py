"""The keyword coverage score: how much of a posting's Requirements the resume answers.

It's for the person to read. Nothing that writes, verifies or renders a Pack reads it, so it
can never push a keyword into a resume.
"""

from typing import Any

from pydantic import BaseModel

from job_copilot import bands

# What a Requirement the resume answers counts for; Missing and Unknown count nothing.
WEIGHTS: dict[str, float] = {"met": 1.0, "partial": 0.5}
# Hard Blockers, such as location or work authorization, aren't keywords a resume answers.
COUNTED_KINDS = ("must_have", "nice_to_have")


class CoveredRequirement(BaseModel):
    requirement: str
    kind: bands.Kind
    result: bands.Result
    # The resume cites Evidence this Requirement Result rests on.
    in_resume: bool


class Coverage(BaseModel):
    # Percent, from 0 to 100.
    score: int
    requirements: list[CoveredRequirement]


def keyword_coverage(requirements: list[dict[str, Any]], cited: set[int]) -> Coverage | None:
    """The score from an Application's Requirement Results and the Evidence its resume cites.

    A Requirement counts when its Result is Met or Partial and the resume cites Evidence the
    Result rests on. None when there's nothing to count.
    """
    counted = [
        CoveredRequirement(
            requirement=r["requirement"],
            kind=r["kind"],
            result=r["result"],
            in_resume=r["result"] in WEIGHTS and bool(cited & set(r.get("evidence_ids", []))),
        )
        for r in requirements
        if r["kind"] in COUNTED_KINDS
    ]
    if not counted:
        return None
    answered = sum(WEIGHTS[r.result] for r in counted if r.in_resume)
    return Coverage(score=round(100 * answered / len(counted)), requirements=counted)
