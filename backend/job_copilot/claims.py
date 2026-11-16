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


# The words that mark a credential, and whether each is one on its own. "PhD" and "Master's" are;
# "Certified" or "Master" are only beside a capitalised name, as in "AWS Certified Developer" or
# "Master of Science", so "Certified the release" and "a Masters programme website" aren't.
CREDENTIAL_WORDS = {
    **dict.fromkeys(
        ["phd", "ph.d", "doctorate", "msc", "bsc", "mba", "mphil", "meng", "beng"], True
    ),
    **dict.fromkeys(["master's", "bachelor's", "masters'", "bachelors'"], True),
    **dict.fromkeys(["certified", "certification", "certificate", "licensed", "licence"], False),
    **dict.fromkeys(["license", "chartered", "accredited", "specialty", "speciality"], False),
    **dict.fromkeys(["master", "masters", "bachelor", "bachelors", "doctor"], False),
}
# Small words a credential's name runs through, as in "PhD in Machine Learning".
NAME_JOINERS = {"in", "of"}
TOKEN = re.compile(r"[\w'.+-]+[,;:.!?)]*")
CLAUSE_END = ",;:.!?)"


def _tokens(text: str) -> list[tuple[str, bool]]:
    """Each word, and whether punctuation ends a clause after it."""
    found = []
    for raw in TOKEN.findall(text):
        word = raw.rstrip(CLAUSE_END)
        found.append((word.rstrip("."), word != raw or raw.endswith(".")))
    return found


def _looks_like_name(word: str) -> bool:
    """A capitalised word or an acronym, as a credential's name is written."""
    return word[:1].isupper() or any(c.isdigit() for c in word)


def _is_acronym(word: str) -> bool:
    return len(word) > 1 and word.isupper()


def _credentials(claim: str) -> list[str]:
    """Each certification, licence or degree a Claim names, with the words naming it.

    The name runs left over acronyms only, as in "AWS Certified", so a lead-in such as "Earned"
    stays out, and stops at punctuation, so a list such as "Python, AWS Certified" does too.

    ponytail: spots credentials by their wording, so a bare acronym such as CISSP or an all
    lowercase one slips past; Verification's prompt asks the model to treat them as facts too.
    """
    tokens = _tokens(claim)
    found = []
    for i, (word, _) in enumerate(tokens):
        on_its_own = CREDENTIAL_WORDS.get(word.casefold())
        if on_its_own is None:
            continue
        start = i
        while start > 0 and not tokens[start - 1][1] and _is_acronym(tokens[start - 1][0]):
            start -= 1
        end = i + 1
        while end < len(tokens) and not tokens[end - 1][1]:
            word_after = tokens[end][0]
            joins = (
                word_after in NAME_JOINERS
                and end + 1 < len(tokens)
                and _looks_like_name(tokens[end + 1][0])
            )
            if not (_looks_like_name(word_after) or joins):
                break
            end += 1
        if not on_its_own and end - start == 1:
            continue
        found.append(" ".join(w for w, _ in tokens[start:end]))
    return found


def _evidence_names(phrase: str, evidence: list[str]) -> bool:
    """Whether some Evidence item has the phrase's words in a row, ignoring case."""
    wanted = [w.casefold() for w, _ in _tokens(phrase)]
    for text in evidence:
        words = [w.casefold() for w, _ in _tokens(text)]
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
        if not _evidence_names(credential, evidence):
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
