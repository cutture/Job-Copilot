from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from job_copilot import profile
from job_copilot.db import UserId, connect, current_user_id

MANUAL_SOURCE = "Manual Source"
TITLE_LENGTH = 120

app = FastAPI(title="Job Copilot")
app.include_router(profile.router)
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
    created_at: datetime


COLUMNS = "id, title, source, text, status, created_at"


@app.post("/api/job-postings", status_code=201)
def paste_posting(posting: PastedPosting, user_id: UserId) -> JobPosting:
    title = next(line.strip() for line in posting.text.splitlines() if line.strip())[:TITLE_LENGTH]
    with connect() as conn:
        row: Any = conn.execute(
            f"""INSERT INTO job_postings (user_id, source, title, text)
                VALUES (%s, %s, %s, %s) RETURNING {COLUMNS}""",
            (user_id, MANUAL_SOURCE, title, posting.text),
        ).fetchone()
        conn.execute(
            "INSERT INTO jobs (user_id, kind, payload) VALUES (%s, 'process_posting', %s)",
            (user_id, Jsonb({"job_posting_id": str(row["id"])})),
        )
    return JobPosting(**row)


@app.get("/api/job-postings")
def list_postings(user_id: UserId) -> list[JobPosting]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {COLUMNS} FROM job_postings WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [JobPosting(**row) for row in rows]
