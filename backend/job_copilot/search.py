"""The Watchlist and the search job that finds new Job Postings from it."""

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from job_copilot import sources
from job_copilot.db import UserId, connect
from job_copilot.profile import ensure_profile

log = logging.getLogger(__name__)
router = APIRouter()

WATCHLIST_FIELDS = "id, name, source, failure, last_checked_at"
# A search still unfinished after this long was stopped, so Search now is free again.
SEARCH_TIMEOUT = timedelta(minutes=30)


def daily_limit() -> int:
    return int(os.environ.get("SEARCHES_PER_DAY", "5"))


def queue_processing(conn: Any, user_id: UUID, posting_id: Any) -> None:
    conn.execute(
        "INSERT INTO jobs (user_id, kind, payload) VALUES (%s, 'process_posting', %s)",
        (user_id, Jsonb({"job_posting_id": str(posting_id)})),
    )


# --- API ---------------------------------------------------------------------------------


class NewWatchlistEntry(BaseModel):
    url: str = Field(max_length=2000)


class WatchlistEntry(BaseModel):
    id: UUID
    name: str
    source: str
    failure: str | None
    last_checked_at: datetime | None


class SearchStatus(BaseModel):
    runs_left: int
    daily_limit: int
    searching: bool


@router.get("/api/watchlist")
def list_watchlist(user_id: UserId) -> list[WatchlistEntry]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {WATCHLIST_FIELDS} FROM watchlist WHERE user_id = %s ORDER BY created_at",
            (user_id,),
        ).fetchall()
    return [WatchlistEntry(**row) for row in rows]


# A plain def runs in a worker thread, so the board lookup doesn't block other requests.
@router.post("/api/watchlist", status_code=201)
def add_to_watchlist(entry: NewWatchlistEntry, user_id: UserId) -> WatchlistEntry:
    board = sources.find_board(entry.url)
    if board is None:
        supported = ", ".join(sources.ADAPTERS)
        raise HTTPException(
            422, f"This careers page isn't supported yet. Supported Sources: {supported}."
        )
    adapter = sources.ADAPTERS[board.source]
    try:
        name = adapter.employer_name(board)
    except (httpx.HTTPError, ValueError, AttributeError):
        raise HTTPException(
            422,
            f"We couldn't find that employer on {board.source}. Check the URL and try again.",
        ) from None
    with connect() as conn:
        row: Any = conn.execute(
            f"""INSERT INTO watchlist (user_id, source, api_host, token, name)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
                RETURNING {WATCHLIST_FIELDS}""",
            (user_id, board.source, board.api_host, board.token, name),
        ).fetchone()
    if row is None:
        raise HTTPException(409, f"{name} is already on your Watchlist.")
    return WatchlistEntry(**row)


@router.delete("/api/watchlist/{entry_id}", status_code=204)
def remove_from_watchlist(entry_id: UUID, user_id: UserId) -> None:
    with connect() as conn:
        # Their postings are no longer checked, so they leave results but stay for Applications.
        conn.execute(
            """UPDATE job_postings SET expired_at = COALESCE(expired_at, now())
               WHERE watchlist_id = %s AND user_id = %s""",
            (entry_id, user_id),
        )
        deleted = conn.execute(
            "DELETE FROM watchlist WHERE id = %s AND user_id = %s RETURNING id",
            (entry_id, user_id),
        ).fetchone()
    if deleted is None:
        raise HTTPException(404, "Not on your Watchlist")


def _search_status(conn: Any, user_id: UUID) -> SearchStatus:
    # ponytail: a day is a UTC day; use the person's time zone once they can set one.
    row: Any = conn.execute(
        """SELECT count(*) FILTER (WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
                                       AT TIME ZONE 'UTC') AS today,
                  count(*) FILTER (WHERE finished_at IS NULL AND created_at > now() - %s)
                    AS running
           FROM searches WHERE user_id = %s""",
        (SEARCH_TIMEOUT, user_id),
    ).fetchone()
    limit = daily_limit()
    return SearchStatus(
        runs_left=max(limit - row["today"], 0), daily_limit=limit, searching=row["running"] > 0
    )


@router.get("/api/search")
def search_status(user_id: UserId) -> SearchStatus:
    with connect() as conn:
        return _search_status(conn, user_id)


def _next_due(conn: Any, user_id: UUID) -> datetime | None:
    """When the first Source may be searched again, or None if one is due now."""
    rows = conn.execute(
        "SELECT source, last_checked_at FROM watchlist WHERE user_id = %s", (user_id,)
    ).fetchall()
    now = datetime.now(UTC)
    earliest = min(
        row["last_checked_at"] + sources.ADAPTERS[row["source"]].poll_interval
        if row["last_checked_at"]
        else now
        for row in rows
    )
    return earliest if earliest > now else None


@router.post("/api/search", status_code=202)
def search_now(user_id: UserId) -> SearchStatus:
    with connect() as conn:
        # One search at a time per person, so two clicks can't both pass the limit check.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"search:{user_id}",))
        if not conn.execute("SELECT 1 FROM watchlist WHERE user_id = %s", (user_id,)).fetchone():
            raise HTTPException(409, "Add an employer to your Watchlist first.")
        next_due = _next_due(conn, user_id)
        if next_due:
            minutes = int((next_due - datetime.now(UTC)).total_seconds() // 60) + 1
            raise HTTPException(
                409,
                "Your Sources were all checked a moment ago. "
                f"Search again in {minutes} minute{'s' if minutes > 1 else ''}.",
            )
        status = _search_status(conn, user_id)
        if status.runs_left == 0:
            raise HTTPException(
                429,
                f"Today's {status.daily_limit} searches are used. "
                "Search is available again tomorrow.",
            )
        row: Any = conn.execute(
            "INSERT INTO searches (user_id) VALUES (%s) RETURNING id", (user_id,)
        ).fetchone()
        conn.execute(
            "INSERT INTO jobs (user_id, kind, payload) VALUES (%s, 'search', %s)",
            (user_id, Jsonb({"search_id": row["id"]})),
        )
        return _search_status(conn, user_id)


# --- Search job --------------------------------------------------------------------------


def _recheck(conn: Any, user_id: UUID, window: int) -> None:
    """After a preference change, run Filter again on postings still in the Search Window."""
    # ponytail: every posting counts as unapplied until Applications exist (#24).
    rows = conn.execute(
        """UPDATE job_postings SET status = 'queued', filter_reason = NULL
           WHERE user_id = %s AND expired_at IS NULL
             AND status IN ('received', 'filtered', 'model_unavailable', 'not_rated')
             AND COALESCE(posted_on, created_at::date) >= current_date - %s
           RETURNING id""",
        (user_id, window),
    ).fetchall()
    for row in rows:
        queue_processing(conn, user_id, row["id"])
    conn.execute("UPDATE profiles SET recheck_due = false WHERE user_id = %s", (user_id,))


def _save_postings(
    conn: Any,
    user_id: UUID,
    entry: dict[str, Any],
    board: sources.Board,
    postings: list[sources.SourcePosting],
    window: int,
) -> None:
    adapter = sources.ADAPTERS[board.source]
    credit_url = adapter.credit_url(board)
    today = datetime.now(UTC).date()
    for posting in postings:
        posted_on = posting.posted_on or today
        if (today - posted_on).days > window or not posting.apply_url.startswith("https://"):
            continue
        row = conn.execute(
            """INSERT INTO job_postings (user_id, source, title, text, watchlist_id, external_id,
                                         employer, posted_on, date_provided, credit_url,
                                         apply_url)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, source, external_id) WHERE external_id IS NOT NULL
               DO NOTHING RETURNING id""",
            (
                user_id,
                board.source,
                posting.title,
                posting.text,
                entry["id"],
                posting.external_id,
                entry["name"],
                posted_on,
                posting.posted_on is not None,
                credit_url,
                posting.apply_url,
            ),
        ).fetchone()
        if row:
            queue_processing(conn, user_id, row["id"])
    if adapter.expires_when_missing:
        listed = [posting.external_id for posting in postings]
        conn.execute(
            """UPDATE job_postings SET expired_at = CASE WHEN external_id = ANY(%s) THEN NULL
                                                         ELSE COALESCE(expired_at, now()) END
               WHERE user_id = %s AND watchlist_id = %s""",
            (listed, user_id, entry["id"]),
        )


def run_search(user_id: UUID, payload: dict[str, Any]) -> None:
    with connect() as conn:
        ensure_profile(conn, user_id)
        profile: Any = conn.execute(
            "SELECT search_window_days, recheck_due FROM profiles WHERE user_id = %s", (user_id,)
        ).fetchone()
        window = profile["search_window_days"]
        if profile["recheck_due"]:
            _recheck(conn, user_id, window)
        entries = conn.execute(
            "SELECT * FROM watchlist WHERE user_id = %s ORDER BY created_at", (user_id,)
        ).fetchall()
    now = datetime.now(UTC)
    for entry in entries:
        adapter = sources.ADAPTERS[entry["source"]]
        checked = entry["last_checked_at"]
        if checked and now - checked < adapter.poll_interval:
            continue
        board = sources.Board(entry["source"], entry["api_host"], entry["token"])
        try:
            postings = adapter.postings(board)
            with connect() as conn:
                _save_postings(conn, user_id, entry, board, postings, window)
                conn.execute(
                    "UPDATE watchlist SET failure = NULL, last_checked_at = now() WHERE id = %s",
                    (entry["id"],),
                )
        except Exception as error:
            # One failing Source never stops the others.
            log.warning("Source %s failed: %s", entry["source"], type(error).__name__)
            failure = (
                f"We couldn't reach {entry['name']} on {entry['source']}. "
                "We'll try again on the next search."
            )
            with connect() as conn:
                conn.execute(
                    "UPDATE watchlist SET failure = %s WHERE id = %s", (failure, entry["id"])
                )
    finish_search(user_id, payload)


def finish_search(user_id: UUID, payload: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE searches SET finished_at = now() WHERE id = %s AND user_id = %s",
            (payload["search_id"], user_id),
        )
