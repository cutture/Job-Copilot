"""Watchlist and Search now journeys. Only Source responses and models are faked."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import rating, sources, worker
from job_copilot.api import app, current_user_id
from tests.conftest import TEST_DB, FakeProvider
from tests.test_filter import facts, prefer
from tests.test_rating import answer

TODAY = datetime.now(UTC).date()


def job(job_id: int, days_old: int | None, title: str = "Applied AI Engineer") -> dict[str, Any]:
    posted = (
        {"first_published": f"{TODAY - timedelta(days=days_old)}T10:00:00+00:00"}
        if days_old is not None
        else {}
    )
    return {
        "id": job_id,
        "title": title,
        "updated_at": f"{TODAY}T10:00:00+00:00",
        **posted,
        "location": {"name": "Remote"},
        "absolute_url": f"https://job-boards.greenhouse.io/board/jobs/{job_id}",
        "content": "&lt;p&gt;Build retrieval systems with Python.&lt;/p&gt;",
    }


@dataclass
class FakeBoards:
    """Greenhouse boards by token: a name and jobs, or an error to raise."""

    names: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    down: set[str] = field(default_factory=set)
    fetched: list[str] = field(default_factory=list)

    def fetch(self, url: str) -> Any:
        self.fetched.append(url)
        token = url.split("/boards/")[1].split("/")[0].split("?")[0]
        if token in self.down:
            raise httpx.ConnectError("down")
        if token not in self.names:
            raise httpx.HTTPStatusError(
                "not found", request=httpx.Request("GET", url), response=httpx.Response(404)
            )
        if "/jobs" in url:
            return {"jobs": self.jobs.get(token, []), "meta": {}}
        return {"name": self.names[token]}


@pytest.fixture
def boards(monkeypatch: pytest.MonkeyPatch, provider: FakeProvider) -> FakeBoards:
    fake = FakeBoards()
    monkeypatch.setattr(sources, "fetch_json", fake.fetch)
    # Searches in a test run back to back, so no Source waits for its poll interval.
    monkeypatch.setattr(sources.GREENHOUSE, "poll_interval", timedelta(seconds=0))
    provider.text = facts()
    provider.answers = {rating.RATING_MODEL: json.dumps(answer())}
    return fake


def watch(client: TestClient, boards: FakeBoards, token: str, name: str) -> dict[str, Any]:
    boards.names[token] = name
    response = client.post(
        "/api/watchlist", json={"url": f"https://job-boards.greenhouse.io/{token}"}
    )
    assert response.status_code == 201, response.text
    entry: dict[str, Any] = response.json()
    return entry


def search(client: TestClient) -> None:
    assert client.post("/api/search").status_code == 202
    while worker.run_once():
        pass


def listed(client: TestClient) -> dict[str, dict[str, Any]]:
    return {p["title"]: p for p in client.get("/api/job-postings").json()}


def test_an_employer_is_added_from_its_careers_url(client: TestClient, boards: FakeBoards) -> None:
    entry = watch(client, boards, "northwindlabs", "Northwind Labs")

    assert (entry["name"], entry["source"]) == ("Northwind Labs", "Greenhouse")
    assert client.get("/api/watchlist").json() == [entry]
    again = client.post(
        "/api/watchlist", json={"url": "https://boards.greenhouse.io/northwindlabs"}
    )
    assert again.status_code == 409


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("https://jobs.lever.co/northwindlabs", "isn't supported yet"),
        ("https://careers.example.com/jobs", "isn't supported yet"),
        ("https://job-boards.greenhouse.io/nosuchboard", "couldn't find a Greenhouse board"),
    ],
)
def test_an_unsupported_or_missing_board_is_explained(
    client: TestClient, boards: FakeBoards, url: str, message: str
) -> None:
    response = client.post("/api/watchlist", json={"url": url})

    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert client.get("/api/watchlist").json() == []


def test_search_now_adds_new_postings_within_the_search_window_through_filter(
    client: TestClient, boards: FakeBoards
) -> None:
    prefer(client)
    watch(client, boards, "northwindlabs", "Northwind Labs")
    boards.jobs["northwindlabs"] = [
        job(1, 3, "Applied AI Engineer"),
        job(2, 15, "Edge Of Window Engineer"),
        job(3, 16, "Too Old Engineer"),
        job(4, None, "Undated Engineer"),
    ]

    search(client)

    postings = listed(client)
    assert set(postings) == {"Applied AI Engineer", "Edge Of Window Engineer", "Undated Engineer"}
    new = postings["Applied AI Engineer"]
    assert (new["source"], new["employer"], new["status"]) == (
        "Greenhouse",
        "Northwind Labs",
        "received",
    )
    assert new["posted_on"] == str(TODAY - timedelta(days=3))
    assert new["credit_url"] == "https://job-boards.greenhouse.io/northwindlabs"
    assert new["apply_url"] == "https://job-boards.greenhouse.io/board/jobs/1"
    undated = postings["Undated Engineer"]
    assert (undated["posted_on"], undated["date_provided"]) == (str(TODAY), False)


def test_a_search_adds_only_postings_not_seen_before_and_keeps_delayed_ones(
    client: TestClient, boards: FakeBoards
) -> None:
    prefer(client)
    watch(client, boards, "northwindlabs", "Northwind Labs")
    boards.jobs["northwindlabs"] = [job(1, 2)]
    search(client)
    # The next search sees the same posting again, plus one published 10 days ago that the
    # board only listed now.
    boards.jobs["northwindlabs"] = [job(1, 2), job(2, 10, "Delayed Engineer")]

    search(client)

    titles = [p["title"] for p in client.get("/api/job-postings").json()]
    assert sorted(titles) == ["Applied AI Engineer", "Delayed Engineer"]


def test_a_shorter_search_window_is_respected_and_15_is_the_most(
    client: TestClient, boards: FakeBoards
) -> None:
    prefer(client, search_window_days=7)
    assert client.get("/api/profile").json()["search_window_days"] == 7
    assert client.put("/api/profile", json={"search_window_days": 16}).status_code == 422
    watch(client, boards, "northwindlabs", "Northwind Labs")
    boards.jobs["northwindlabs"] = [job(1, 7, "Week Old Engineer"), job(2, 8, "Older Engineer")]

    search(client)

    assert set(listed(client)) == {"Week Old Engineer"}


def test_one_failing_source_doesnt_stop_the_others_and_its_failure_is_shown(
    client: TestClient, boards: FakeBoards
) -> None:
    prefer(client)
    watch(client, boards, "northwindlabs", "Northwind Labs")
    watch(client, boards, "contoso", "Contoso")
    boards.jobs["contoso"] = [job(1, 1, "Contoso Engineer")]
    boards.down.add("northwindlabs")

    search(client)

    assert set(listed(client)) == {"Contoso Engineer"}
    entries = {e["name"]: e for e in client.get("/api/watchlist").json()}
    assert entries["Northwind Labs"]["failure"] == (
        "Northwind Labs's Greenhouse board didn't respond. We'll try again on the next search."
    )
    assert entries["Contoso"]["failure"] is None


def test_postings_from_a_source_that_was_down_arent_lost(
    client: TestClient, boards: FakeBoards
) -> None:
    prefer(client)
    watch(client, boards, "northwindlabs", "Northwind Labs")
    boards.jobs["northwindlabs"] = [job(1, 5)]
    boards.down.add("northwindlabs")
    search(client)
    boards.down.clear()

    search(client)

    assert set(listed(client)) == {"Applied AI Engineer"}
    assert client.get("/api/watchlist").json()[0]["failure"] is None


def test_an_expired_posting_leaves_results_but_is_kept(
    client: TestClient, boards: FakeBoards
) -> None:
    prefer(client)
    watch(client, boards, "northwindlabs", "Northwind Labs")
    boards.jobs["northwindlabs"] = [job(1, 2), job(2, 2, "Closing Engineer")]
    search(client)
    boards.jobs["northwindlabs"] = [job(1, 2)]

    search(client)

    assert set(listed(client)) == {"Applied AI Engineer"}
    # Kept so an Application can stay attached to it.
    everything = client.get("/api/job-postings", params={"include_expired": True}).json()
    expired = [p for p in everything if p["expired"]]
    assert [p["title"] for p in expired] == ["Closing Engineer"]


def test_search_now_respects_the_daily_run_limit(
    client: TestClient, boards: FakeBoards, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEARCHES_PER_DAY", "2")
    watch(client, boards, "northwindlabs", "Northwind Labs")
    assert client.get("/api/search").json() == {
        "runs_left": 2,
        "daily_limit": 2,
        "searching": False,
    }

    search(client)
    assert client.post("/api/search").json()["runs_left"] == 0
    assert client.get("/api/search").json()["searching"] is True

    refused = client.post("/api/search")
    assert refused.status_code == 429
    assert (
        refused.json()["detail"]
        == "Today's 2 searches are used. Search is available again tomorrow."
    )


def test_the_daily_limit_defaults_to_5(client: TestClient, boards: FakeBoards) -> None:
    assert client.get("/api/search").json()["daily_limit"] == 5


def test_search_needs_an_employer_on_the_watchlist(client: TestClient) -> None:
    response = client.post("/api/search")

    assert response.status_code == 409
    assert client.get("/api/search").json()["runs_left"] == 5


def test_a_source_is_polled_no_more_often_than_it_declares(
    client: TestClient, boards: FakeBoards, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sources.GREENHOUSE, "poll_interval", timedelta(hours=1))
    watch(client, boards, "northwindlabs", "Northwind Labs")
    boards.fetched.clear()

    search(client)
    search(client)

    assert len([url for url in boards.fetched if "/jobs" in url]) == 1


def test_after_a_preference_change_the_next_search_rechecks_postings_in_the_window(
    client: TestClient, boards: FakeBoards, provider: FakeProvider
) -> None:
    prefer(client, work_type="employment")
    watch(client, boards, "northwindlabs", "Northwind Labs")
    boards.jobs["northwindlabs"] = [job(1, 2, "Freelance AI Engineer")]
    provider.text = facts(title="Freelance AI Engineer", posting_type="freelance")
    search(client)
    assert listed(client)["Freelance AI Engineer"]["status"] == "filtered"

    prefer(client, work_type="employment_and_freelance")
    search(client)

    assert listed(client)["Freelance AI Engineer"]["status"] == "received"


def test_a_pasted_posting_is_always_added_and_has_no_posting_date(
    client: TestClient, boards: FakeBoards
) -> None:
    created = client.post("/api/job-postings", json={"text": "Applied AI Engineer\nRemote"})

    posting = created.json()
    assert (posting["source"], posting["posted_on"], posting["date_provided"]) == (
        "Manual Source",
        None,
        True,
    )


def test_each_person_has_their_own_watchlist(client: TestClient, boards: FakeBoards) -> None:
    watch(client, boards, "northwindlabs", "Northwind Labs")
    other = UUID("00000000-0000-0000-0000-000000000002")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (other,))
    app.dependency_overrides[current_user_id] = lambda: other
    try:
        assert client.get("/api/watchlist").json() == []
        assert client.post("/api/search").status_code == 409
    finally:
        app.dependency_overrides.clear()
