from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from job_copilot import (
    applications,
    challengers,
    deletion,
    downloads,
    eval_runs,
    export,
    form_answers,
    gateway,
    model_settings,
    profile,
    rating,
    retention,
    search,
    sources,
    spending,
)
from job_copilot.db import UserId, connect, current_user_id
from job_copilot.sources import MAX_POSTING_LENGTH, MAX_TITLE_LENGTH

MANUAL_SOURCE = "Manual Source"

app = FastAPI(title="Job Copilot")
app.include_router(profile.router)
app.include_router(search.router)
app.include_router(applications.router)
app.include_router(form_answers.router)
app.include_router(downloads.router)
app.include_router(deletion.router)
app.include_router(export.router)
app.include_router(eval_runs.router)
app.include_router(spending.router)
app.include_router(model_settings.router)
app.include_router(challengers.router)

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
    text: str = Field(max_length=MAX_POSTING_LENGTH)

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
    credit_text: str | None = None
    apply_url: str | None
    expired: bool
    # When a Filtered Posting is deleted.
    deletes_on: date | None = None
    # The Application started by clicking Apply, if there is one.
    application_id: UUID | None = None
    rating_state: rating.RatingState | None = None
    match: rating.MatchView | None = None
    # A Rescore of its Match is queued or running.
    rescoring: bool = False


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
MATCH_FIELDS = (
    "band",
    "reasons",
    "gaps",
    "profile_prompts",
    "nice_met",
    "requirements",
    "profile_changed",
    "seniority",
    "previous_band",
)


@app.post("/api/job-postings", status_code=201)
def paste_posting(posting: PastedPosting, user_id: UserId) -> JobPosting:
    title = next(line.strip() for line in posting.text.splitlines() if line.strip())[
        :MAX_TITLE_LENGTH
    ]
    with connect() as conn:
        row: Any = conn.execute(
            f"""INSERT INTO job_postings (user_id, source, title, text)
                VALUES (%s, %s, %s, %s) RETURNING {COLUMNS}""",
            (user_id, MANUAL_SOURCE, title, posting.text),
        ).fetchone()
        search.queue_processing(conn, user_id, row["id"])
    return JobPosting(**row, expired=False)


@app.post("/api/job-postings/{posting_id}/retry-rating", status_code=202)
def retry_rating(posting_id: UUID, user_id: UserId) -> None:
    """Rate a posting that couldn't be rated again, starting a paused rating step at once."""
    with connect() as conn:
        updated = conn.execute(
            """UPDATE job_postings SET status = 'received'
               WHERE id = %s AND user_id = %s AND status = 'not_rated'""",
            (posting_id, user_id),
        ).rowcount
    if not updated:
        raise HTTPException(409, "This Job Posting isn't waiting to be rated again.")
    gateway.resume_steps(user_id, gateway.JOB_STEPS["rate_match"])
    rating.queue_ratings(user_id)


class RescoreRequest(BaseModel):
    job_posting_ids: list[UUID] = Field(min_length=1, max_length=rating.MAX_RESCORE)


@app.post("/api/rescore/estimate")
def estimate_rescore(request: RescoreRequest, user_id: UserId) -> rating.RescoreEstimate:
    """What Rescoring these Matches should cost, shown before anything runs."""
    return rating.rescore_estimate(user_id, request.job_posting_ids)


@app.post("/api/rescore", status_code=202)
def rescore(request: RescoreRequest, user_id: UserId) -> None:
    """Judge these Matches again against the Profile now. Never automatic; a Match already
    applied to keeps the rating saved at Apply."""
    if rating.rescorable(user_id, request.job_posting_ids) != len(set(request.job_posting_ids)):
        raise HTTPException(
            409,
            "Only rated Matches you haven't applied to can be Rescored. An applied Match keeps "
            "the rating it had when you applied.",
        )
    gateway.resume_steps(user_id, gateway.JOB_STEPS["rescore_match"])
    rating.queue_rescores(user_id, request.job_posting_ids)


def _credit_text(source: str) -> str | None:
    adapter = sources.ADAPTERS.get(source)
    return adapter.credit_text if adapter else None


@app.get("/api/job-postings")
def list_postings(user_id: UserId) -> list[JobPosting]:
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT {", ".join(f"p.{f}" for f in POSTING_FIELDS)},
                       {", ".join(f"m.{f}" for f in MATCH_FIELDS)},
                       p.expired_at IS NOT NULL AS expired, a.id AS application_id,
                       CASE WHEN p.status = 'filtered' AND a.id IS NULL
                            THEN {retention.FILTERED_DELETES_ON} END AS deletes_on,
                       CASE WHEN p.status <> 'received' THEN NULL
                            WHEN m.job_posting_id IS NOT NULL THEN 'rated'
                            WHEN {rating.RATING_QUEUED} THEN 'rating'
                            ELSE 'waiting' END AS rating_state,
                       COALESCE({rating.RESCORING}, false) AS rescoring
                FROM job_postings p LEFT JOIN matches m ON m.job_posting_id = p.id
                LEFT JOIN applications a ON a.job_posting_id = p.id AND a.user_id = p.user_id
                WHERE p.user_id = %s AND p.expired_at IS NULL
                ORDER BY p.created_at DESC""",
            (user_id,),
        ).fetchall()
    return [
        JobPosting(
            **{f: row[f] for f in POSTING_FIELDS},
            expired=row["expired"],
            deletes_on=row["deletes_on"],
            application_id=row["application_id"],
            credit_text=_credit_text(row["source"]),
            rating_state=row["rating_state"],
            rescoring=row["rescoring"],
            match=rating.MatchView(**{f: row[f] for f in MATCH_FIELDS})
            if row["rating_state"] == "rated"
            else None,
        )
        for row in rows
    ]
