from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from job_copilot import profile, rating, search
from job_copilot.db import UserId, connect, current_user_id

MANUAL_SOURCE = "Manual Source"
TITLE_LENGTH = 120

app = FastAPI(title="Job Copilot")
app.include_router(profile.router)
app.include_router(search.router)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def refuse_cross_site_changes(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    # Local mode has no login, so another website could otherwise make the person's browser
    # change their data here. Browsers mark where a request came from; non-browser clients
    # send no mark and are allowed.
    site = request.headers.get("sec-fetch-site")
    if request.method in UNSAFE_METHODS and site not in (None, "same-origin", "none"):
        return JSONResponse({"detail": "Cross-site requests aren't allowed"}, status_code=403)
    return await call_next(request)


__all__ = ["app", "current_user_id"]


class PastedPosting(BaseModel):
    text: str = Field(max_length=100_000)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.replace(chr(0), "").strip():
            raise ValueError("Paste the Job Posting text")
        return value.replace(chr(0), "")  # Postgres can't store NUL characters.


class JobPosting(BaseModel):
    id: UUID
    title: str
    source: str
    text: str
    status: str
    posting_type: str | None
    filter_reason: str | None
    salary_note: str | None
    created_at: datetime
    employer: str | None
    # The original publish date from the Source; pasted postings have none.
    posted_on: date | None
    date_provided: bool
    credit_url: str | None
    apply_url: str | None
    expired: bool
    rating_state: rating.RatingState | None = None
    match: rating.MatchView | None = None


POSTING_FIELDS = (
    "id",
    "title",
    "source",
    "text",
    "status",
    "posting_type",
    "filter_reason",
    "salary_note",
    "created_at",
    "employer",
    "posted_on",
    "date_provided",
    "credit_url",
    "apply_url",
)
COLUMNS = ", ".join(POSTING_FIELDS)
MATCH_FIELDS = ("band", "reasons", "gaps", "profile_prompts", "nice_met", "requirements")


@app.post("/api/job-postings", status_code=201)
def paste_posting(posting: PastedPosting, user_id: UserId) -> JobPosting:
    title = next(line.strip() for line in posting.text.splitlines() if line.strip())[:TITLE_LENGTH]
    with connect() as conn:
        row: Any = conn.execute(
            f"""INSERT INTO job_postings (user_id, source, title, text)
                VALUES (%s, %s, %s, %s) RETURNING {COLUMNS}""",
            (user_id, MANUAL_SOURCE, title, posting.text),
        ).fetchone()
        search.queue_processing(conn, user_id, row["id"])
    return JobPosting(**row, expired=False)


@app.get("/api/job-postings")
def list_postings(user_id: UserId, include_expired: bool = False) -> list[JobPosting]:
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT {", ".join(f"p.{f}" for f in POSTING_FIELDS)},
                       {", ".join(f"m.{f}" for f in MATCH_FIELDS)},
                       p.expired_at IS NOT NULL AS expired,
                       CASE WHEN p.status <> 'received' THEN NULL
                            WHEN m.job_posting_id IS NOT NULL THEN 'rated'
                            WHEN {rating.RATING_QUEUED} THEN 'rating'
                            ELSE 'waiting' END AS rating_state
                FROM job_postings p LEFT JOIN matches m ON m.job_posting_id = p.id
                WHERE p.user_id = %s AND (%s OR p.expired_at IS NULL)
                ORDER BY p.created_at DESC""",
            (user_id, include_expired),
        ).fetchall()
    return [
        JobPosting(
            **{f: row[f] for f in POSTING_FIELDS},
            expired=row["expired"],
            rating_state=row["rating_state"],
            match=rating.MatchView(**{f: row[f] for f in MATCH_FIELDS})
            if row["rating_state"] == "rated"
            else None,
        )
        for row in rows
    ]
