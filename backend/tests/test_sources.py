"""The shared Source adapter contract, run against every adapter with saved responses."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from job_copilot import sources

SAVED = Path(__file__).parent / "saved_responses"
# A careers URL for each adapter's invented saved board.
CAREERS_URLS = {"Greenhouse": "https://job-boards.greenhouse.io/northwindlabs"}
# The posting dates in each adapter's saved responses, by posting ID.
POSTED = {"Greenhouse": {"4001": date(2026, 10, 28), "4002": None}}


def saved(source: str) -> Any:
    def fetch(url: str) -> Any:
        name = "jobs.json" if "/jobs" in url else "board.json"
        return json.loads((SAVED / source.lower() / name).read_text(encoding="utf-8"))

    return fetch


@pytest.fixture(params=sorted(sources.ADAPTERS))
def adapter(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> sources.Adapter:
    source: str = request.param
    monkeypatch.setattr(sources, "fetch_json", saved(source))
    return sources.ADAPTERS[source]


def test_every_adapter_has_saved_responses_and_a_careers_url() -> None:
    assert set(sources.ADAPTERS) == set(CAREERS_URLS) == set(POSTED)


def test_an_adapter_declares_its_rules(adapter: sources.Adapter) -> None:
    assert adapter.date_field
    assert adapter.poll_interval.total_seconds() > 0
    assert adapter.credit_text
    assert adapter.apply_url_field
    assert isinstance(adapter.expires_when_missing, bool)


def test_an_adapter_reads_a_careers_url_and_the_employer_name(adapter: sources.Adapter) -> None:
    board = sources.find_board(CAREERS_URLS[adapter.source])

    assert board is not None and board.source == adapter.source
    assert adapter.employer_name(board) == "Northwind Labs"
    assert adapter.credit_url(board).startswith("https://")


def test_an_adapter_normalises_postings(adapter: sources.Adapter) -> None:
    board = sources.find_board(CAREERS_URLS[adapter.source])
    assert board is not None

    postings = adapter.postings(board)

    assert {p.external_id: p.posted_on for p in postings} == POSTED[adapter.source]
    for posting in postings:
        assert posting.title and posting.location
        assert posting.location in posting.text and posting.title in posting.text
        assert (
            "<" not in posting.text and "&amp;" not in posting.text and "&lt;" not in posting.text
        )
        assert posting.apply_url.startswith("https://")


def test_the_greenhouse_posting_date_is_first_published_never_updated_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sources, "fetch_json", saved("Greenhouse"))
    board = sources.find_board(CAREERS_URLS["Greenhouse"])
    assert board is not None

    posted = {p.external_id: p.posted_on for p in sources.GREENHOUSE.postings(board)}

    assert sources.GREENHOUSE.date_field == "first_published"
    # 4002 has only updated_at, so its date isn't provided.
    assert posted == {"4001": date(2026, 10, 28), "4002": None}


@pytest.mark.parametrize(
    ("url", "token", "api_host"),
    [
        ("https://boards.greenhouse.io/northwindlabs", "northwindlabs", "boards-api.greenhouse.io"),
        (
            "https://job-boards.greenhouse.io/northwindlabs/jobs/4001?gh_src=x",
            "northwindlabs",
            "boards-api.greenhouse.io",
        ),
        (
            "https://job-boards.eu.greenhouse.io/northwindlabs",
            "northwindlabs",
            "boards-api.eu.greenhouse.io",
        ),
        (
            "https://boards.greenhouse.io/embed/job_board?for=northwindlabs",
            "northwindlabs",
            "boards-api.greenhouse.io",
        ),
    ],
)
def test_greenhouse_careers_urls_are_recognised(url: str, token: str, api_host: str) -> None:
    board = sources.find_board(url)

    assert board is not None
    assert (board.source, board.token, board.api_host) == ("Greenhouse", token, api_host)


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.lever.co/northwindlabs",
        "https://careers.example.com/jobs",
        "http://boards.greenhouse.io/northwindlabs",
        "https://boards.greenhouse.io.example.com/northwindlabs",
        "https://boards.greenhouse.io/",
        "https://boards.greenhouse.io/../admin",
        "not a url",
    ],
)
def test_other_urls_are_unsupported(url: str) -> None:
    assert sources.find_board(url) is None
