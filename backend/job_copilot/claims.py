"""Claim rules: exact checks Verification makes in code, with no model or database.

A number, link or email address in a Claim must appear in the Evidence it cites, so text a
posting slipped into a draft can't carry one through. A count of years may instead be covered by
a dated range in that Evidence, such as "Jan 2021 to present".
"""

import re
from datetime import date

YEARS_CLAIM = re.compile(r"(\d+(?:\.\d+)?)(\s*\+)?\s*years?\b", re.IGNORECASE)
LINK = re.compile(r"(?:https?://|www\.)[^\s<>\"']+|[^\s<>\"'@]+@[^\s<>\"'@]+\.\w+", re.IGNORECASE)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
DATED_RANGE = re.compile(
    r"\b((?:19|20)\d{2})\s*(?:-|–|—|to|until)\s*(?:[A-Za-z]+\.?\s+)?"
    r"((?:19|20)\d{2}|present|now|current|today)\b",
    re.IGNORECASE,
)


def years_shown(evidence: list[str], today: date) -> int:
    """The longest span of years any dated range in the Evidence covers."""
    spans = [0]
    for text in evidence:
        for start, end in DATED_RANGE.findall(text):
            last = int(end) if end.isdigit() else today.year
            spans.append(last - int(start))
    return max(spans)


def _value(token: str) -> str:
    return token.rstrip("%").replace(",", "")


def unsupported_detail(claim: str, evidence: list[str], today: date) -> str | None:
    """The first number, link or email in the Claim its Evidence doesn't show, if any."""
    cited = " ".join(evidence).casefold()
    for link in LINK.findall(claim):
        if link.rstrip(".,;:!?)").casefold() not in cited:
            return str(link)
    claim = LINK.sub(" ", claim)
    shown = {_value(token) for text in evidence for token in NUMBER.findall(text)}
    for match in YEARS_CLAIM.finditer(claim):
        years = float(match[1])
        if match[1] not in shown and years > years_shown(evidence, today):
            return " ".join(match[0].replace(" +", "+").split())
    rest = YEARS_CLAIM.sub(" ", claim)
    for token in NUMBER.findall(rest):
        if _value(token) not in shown:
            return str(token)
    return None
