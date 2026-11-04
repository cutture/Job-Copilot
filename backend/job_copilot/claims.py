"""Claim rules: exact checks Verification makes in code, with no model or database.

A number, link or email address in a Claim must appear in the Evidence it cites, so text a
posting slipped into a draft can't carry one through. A count of years may instead be covered by
a dated range in that Evidence, such as "Jan 2021 to present".
"""

import re
from datetime import date

YEARS_CLAIM = re.compile(r"(\d+(?:\.\d+)?)(\s*\+)?\s*years?\b", re.IGNORECASE)
# An email, a link with a scheme, or a bare host name such as example.com/jobs. Names like
# Node.js count too, so the Evidence must name them the same way.
LINK = re.compile(
    r"[^\s<>\"'@]+@[^\s<>\"'@]+\.\w+"
    r"|https?://[^\s<>\"']+"
    r"|\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)
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


def _link(token: str) -> str:
    return str(token).rstrip(".,;:!?)").casefold()


def _value(token: str) -> str:
    return token.rstrip("%").replace(",", "")


def unsupported_detail(claim: str, evidence: list[str], today: date) -> str | None:
    """The first number, link or email in the Claim its Evidence doesn't show, if any."""
    links = {_link(token) for text in evidence for token in LINK.findall(text)}
    for token in LINK.findall(claim):
        if _link(token) not in links:
            return str(token)
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
