"""Sources: one small adapter per job board, each declaring its rules.

The search job enforces the declared rules centrally. The app only calls each board's public
API at fixed hosts, so a pasted careers URL is read for its board name and never fetched.
"""

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from job_copilot.profile import strip_controls

FETCH_TIMEOUT_SECONDS = 15
MAX_POSTING_LENGTH = 100_000
MAX_TITLE_LENGTH = 120
TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def fetch_json(url: str) -> Any:
    """The one way the app calls a Source. Tests replace it with saved responses."""
    response = httpx.get(url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False)
    response.raise_for_status()
    return response.json()


@dataclass(frozen=True)
class Board:
    source: str
    api_host: str
    token: str


@dataclass(frozen=True)
class SourcePosting:
    external_id: str
    title: str
    location: str
    text: str
    # The original publish date, or None when the Source doesn't provide one.
    posted_on: date | None
    apply_url: str


class _PlainText(HTMLParser):
    BLOCKS = {"p", "br", "li", "ul", "ol", "div", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(markup: str) -> str:
    parser = _PlainText()
    parser.feed(markup)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def _https(url: Any) -> str | None:
    return url if isinstance(url, str) and url.startswith("https://") else None


class Greenhouse:
    source = "Greenhouse"
    date_field = "first_published"
    # ponytail: Greenhouse publishes no polling limit; 15 minutes keeps repeat searches polite.
    poll_interval = timedelta(minutes=15)
    credit_text = "Greenhouse job board"
    # A posting gone from the board's list has closed.
    expires_when_missing = True
    HOSTS = {
        "boards.greenhouse.io": "boards-api.greenhouse.io",
        "job-boards.greenhouse.io": "boards-api.greenhouse.io",
        "boards.eu.greenhouse.io": "boards-api.eu.greenhouse.io",
        "job-boards.eu.greenhouse.io": "boards-api.eu.greenhouse.io",
    }

    def board(self, url: str) -> Board | None:
        parts = urlsplit(url.strip())
        api_host = self.HOSTS.get(parts.hostname or "")
        if parts.scheme != "https" or api_host is None:
            return None
        segments = [s for s in parts.path.split("/") if s]
        if segments[:2] == ["embed", "job_board"]:
            token = parse_qs(parts.query).get("for", [""])[0]
        else:
            token = segments[0] if segments else ""
        return Board(self.source, api_host, token) if TOKEN.match(token) else None

    def _api(self, board: Board) -> str:
        return f"https://{board.api_host}/v1/boards/{board.token}"

    def employer_name(self, board: Board) -> str:
        name = strip_controls(str(fetch_json(self._api(board)).get("name") or ""))
        return name[:MAX_TITLE_LENGTH] or board.token

    def credit_url(self, board: Board) -> str:
        host = (
            "job-boards.eu.greenhouse.io"
            if ".eu." in board.api_host
            else "job-boards.greenhouse.io"
        )
        return f"https://{host}/{board.token}"

    def postings(self, board: Board) -> list[SourcePosting]:
        answer = fetch_json(f"{self._api(board)}/jobs?content=true")
        postings = []
        for job in answer.get("jobs") or []:
            title = strip_controls(str(job.get("title") or ""))[:MAX_TITLE_LENGTH]
            apply_url = _https(job.get("absolute_url"))
            if not title or job.get("id") is None or apply_url is None:
                continue
            location = strip_controls(str((job.get("location") or {}).get("name") or ""))
            body = plain_text(html.unescape(str(job.get("content") or "")))
            text = "\n".join(part for part in (title, location, body) if part)
            postings.append(
                SourcePosting(
                    external_id=str(job["id"]),
                    title=title,
                    location=location,
                    text=text.replace(chr(0), "")[:MAX_POSTING_LENGTH],
                    posted_on=_date(job.get(self.date_field)),
                    apply_url=apply_url,
                )
            )
        return postings


def _date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(value).date() if isinstance(value, str) else None
    except ValueError:
        return None


Adapter = Greenhouse
GREENHOUSE = Greenhouse()
ADAPTERS: dict[str, Adapter] = {GREENHOUSE.source: GREENHOUSE}


def find_board(url: str) -> Board | None:
    for adapter in ADAPTERS.values():
        board = adapter.board(url)
        if board:
            return board
    return None
