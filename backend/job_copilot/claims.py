"""Claim rules: exact checks Verification makes in code, with no model or database.

A number, link or email address in a Claim must appear in the Evidence it cites, so text a
posting slipped into a draft can't carry one through. A count of years may instead be covered by
a dated range in that Evidence, such as "Jan 2021 to present". A certification, licence or
degree must be named by that Evidence too, word for word: a posting that asks for one is the
likeliest place for a writer to invent it.
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


# Degree names that are a credential on their own.
DEGREES = {"phd", "ph.d", "doctorate", "msc", "bsc", "mba", "mphil", "meng", "beng"}
DEGREES |= {"master's", "bachelor's", "masters'", "bachelors'"}
# Words that name a credential only beside its capitalised name, as in "AWS Certified Developer".
CREDENTIAL_WORDS = {"certified", "certification", "certificate", "licensed", "licence", "license"}
CREDENTIAL_WORDS |= {"chartered", "accredited", "specialty", "speciality", "masters", "bachelors"}
# Small words a credential's name runs through, as in "PhD in Machine Learning".
JOINING = {"in", "of"}
WORD = re.compile(r"[\w'.+-]+")


def _named(word: str) -> bool:
    """A capitalised word or an acronym, as a credential's name is written."""
    return word[:1].isupper() or any(c.isdigit() for c in word)


def _words(text: str) -> list[str]:
    return [w.strip(".,;:!?()").casefold() for w in WORD.findall(text)]


def _credentials(claim: str) -> list[str]:
    """Each certification, licence or degree a Claim names, with the words naming it.

    ponytail: spots credentials by their wording, so an unusual one can slip past; Verification's
    prompt asks the model to treat them as facts too.
    """
    words = [w.strip(".,;:!?()") for w in WORD.findall(claim)]
    found = []
    for i, word in enumerate(words):
        key = word.casefold()
        if key not in DEGREES and key not in CREDENTIAL_WORDS:
            continue
        start = i
        while start > 0 and _named(words[start - 1]) and words[start - 1] != "I":
            start -= 1
        end = i + 1
        while end < len(words) and (
            _named(words[end])
            or (words[end] in JOINING and end + 1 < len(words) and _named(words[end + 1]))
        ):
            end += 1
        if key in CREDENTIAL_WORDS and end - start == 1:
            continue  # "Certified the release" names no credential.
        found.append(" ".join(words[start:end]))
    return found


def _named_in(phrase: str, evidence: list[str]) -> bool:
    wanted = _words(phrase)
    for text in evidence:
        words = _words(text)
        if any(words[i : i + len(wanted)] == wanted for i in range(len(words))):
            return True
    return False


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
    """The first number, link, email or credential in the Claim its Evidence doesn't show."""
    for credential in _credentials(claim):
        if not _named_in(credential, evidence):
            return credential
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
