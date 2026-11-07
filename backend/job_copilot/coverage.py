"""Keyword coverage: how much of a posting's Requirements the resume answers.

It's for the person to read. Nothing that writes, verifies or renders a Pack reads it, so it
can never push a keyword into a resume.
"""

from pydantic import BaseModel

from job_copilot import bands
from job_copilot.rating import RequirementView

# What a Requirement the resume answers counts for; Missing and Unknown count nothing.
WEIGHTS: dict[str, float] = {"met": 1.0, "partial": 0.5}
# Hard Blockers, such as location or work authorization, aren't keywords a resume answers.
COUNTED_KINDS = ("must_have", "nice_to_have")


class CountedRequirement(BaseModel):
    requirement: str
    kind: bands.Kind
    result: bands.Result
    # Whether the resume cites Evidence the Result rests on; None for Missing or Unknown.
    in_resume: bool | None


class Coverage(BaseModel):
    # Percent, from 0 to 100.
    score: int
    counted: list[CountedRequirement]


def keyword_coverage(requirements: list[RequirementView], cited: set[int]) -> Coverage | None:
    """Keyword coverage from an Application's Requirement Results and the Evidence its resume
    cites. None when there's nothing to count.

    A Requirement counts when its Result is Met or Partial and the resume cites Evidence the
    Result rests on. A Submitted resume still cites Evidence deleted since, as it was sent.
    """
    counted = []
    for r in requirements:
        answered = r.result in WEIGHTS
        # A Result resting on no Evidence item, such as one a Profile fact decides or one rated
        # before Evidence IDs were kept, can't be traced to the resume.
        if r.kind not in COUNTED_KINDS or (answered and not r.evidence_ids):
            continue
        counted.append(
            CountedRequirement(
                requirement=r.requirement,
                kind=r.kind,
                result=r.result,
                in_resume=bool(cited & set(r.evidence_ids)) if answered else None,
            )
        )
    if not counted:
        return None
    score = sum(WEIGHTS[r.result] for r in counted if r.in_resume)
    return Coverage(score=round(100 * score / len(counted)), counted=counted)
