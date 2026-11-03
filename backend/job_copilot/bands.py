"""Band rules: deterministic code with no model or database dependency.

Rules apply in order: Low, then Medium, then High. Nice-to-haves never change the Band, and
aren't counted as clear Requirements.
"""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["hard_blocker", "must_have", "nice_to_have"]
Result = Literal["met", "partial", "missing", "unknown"]
# How the person's seniority compares with the posting's. "two_off_firm" means below a minimum
# the posting states firmly; "unknown" means the Profile has no seniority.
Seniority = Literal["fits", "one_off", "two_off", "two_off_firm", "unknown"]
Band = Literal["High", "Medium", "Low"]

MAX_REASONS = 3
KIND_ORDER = {"hard_blocker": 0, "must_have": 1, "nice_to_have": 2}
SENIORITY_HOLDS_BACK = {
    "one_off": "Held back: seniority is one level off",
    "two_off": "Held back: seniority is two or more levels off",
    "unknown": "Held back: your seniority isn't in your Profile",
}


@dataclass(frozen=True)
class JudgedRequirement:
    text: str
    kind: Kind
    result: Result


@dataclass(frozen=True)
class BandResult:
    band: Band
    reasons: list[str]
    gaps: list[str]
    nice_met: int


def _names(requirements: list[JudgedRequirement]) -> str:
    return ", ".join(r.text for r in requirements)


def rate(requirements: list[JudgedRequirement], seniority: Seniority) -> BandResult:
    # Sorted, so the Band and reasons don't depend on the order the model listed things in.
    ordered = sorted(requirements, key=lambda r: (KIND_ORDER[r.kind], r.text, r.result))
    blockers = [r for r in ordered if r.kind == "hard_blocker" and r.result == "missing"]
    # A Hard Blocker that can't be judged, as when a Profile field is empty, counts as an
    # Unknown must-have rather than a Hard Blocker.
    musts = [r for r in ordered if r.kind != "nice_to_have" and r not in blockers]
    lacking = [r for r in musts if r.result in ("missing", "unknown")]
    partial = [r for r in musts if r.result == "partial"]
    nice_met = sum(r.kind == "nice_to_have" and r.result == "met" for r in ordered)
    gaps = [
        f"{r.text}: no Evidence found"
        if r.result in ("missing", "unknown")
        else f"{r.text}: Partial"
        for r in ordered
        if r.result != "met"
    ]

    positives = []
    if not lacking:
        positives.append("All must-haves are backed by Evidence")
    elif len(lacking) < len(musts):
        positives.append(
            f"{len(musts) - len(lacking)} of {len(musts)} must-haves are backed by Evidence"
        )
    if seniority == "fits":
        positives.append("Seniority fits")
    if nice_met:
        positives.append(f"{nice_met} nice-to-have{'s' if nice_met > 1 else ''} met")

    low = [f"Hard Blocker: {r.text}" for r in blockers]
    if seniority == "two_off_firm":
        low.append("Below the posting's firm seniority minimum")
    if len(lacking) >= 2:
        low.append(f"{len(lacking)} must-haves have no Evidence: {_names(lacking)}")
    if low:
        return BandResult("Low", (low + positives)[:MAX_REASONS], gaps, nice_met)

    held_back = []
    if len(lacking) == 1:
        held_back.append(f"Held back by one must-have: {lacking[0].text}")
    if len(partial) >= 2:
        held_back.append(f"Held back by {len(partial)} Partial Requirements: {_names(partial)}")
    if seniority in SENIORITY_HOLDS_BACK:
        held_back.append(SENIORITY_HOLDS_BACK[seniority])
    if len(musts) + len(blockers) < 3:
        held_back.append("Held back: fewer than three clear Requirements")
    if held_back:
        return BandResult("Medium", (held_back + positives)[:MAX_REASONS], gaps, nice_met)

    return BandResult("High", positives[:MAX_REASONS], gaps, nice_met)
