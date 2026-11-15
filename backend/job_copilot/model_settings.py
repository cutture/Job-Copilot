"""Settings for which models run: whether paid or free models are in use, and why, and
Groq's Zero Data Retention confirmation."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from job_copilot import gateway
from job_copilot.db import UserId, connect

router = APIRouter()


class ModelSettings(BaseModel):
    mode: Literal["paid", "free"]
    # Why free models are in use, and what to do about it, when they are.
    note: str | None
    groq_zdr_confirmed: bool
    # True when free models are in use and none may receive personal data yet.
    personal_work_waits: bool


class GroqZdr(BaseModel):
    confirmed: bool


@router.get("/api/model-settings")
def get_model_settings(user_id: UserId) -> ModelSettings:
    status = gateway.model_status(user_id)
    return ModelSettings(
        mode="paid" if status.paid else "free",
        note=status.note,
        groq_zdr_confirmed=status.groq_zdr_confirmed,
        personal_work_waits=status.personal_work_waits,
    )


@router.put("/api/model-settings/groq-zdr")
def set_groq_zdr(new: GroqZdr, user_id: UserId) -> ModelSettings:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET groq_zdr_confirmed = %s WHERE id = %s", (new.confirmed, user_id)
        )
    return get_model_settings(user_id)
