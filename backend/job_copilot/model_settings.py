"""Settings for which models run: whether paid or free models are in use, and why, and
Groq's Zero Data Retention confirmation."""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from job_copilot import gateway
from job_copilot.db import UserId, connect

router = APIRouter()

NO_KEY = "No Anthropic key is set, so free models that don't train on your data are in use."


class ModelSettings(BaseModel):
    mode: Literal["paid", "free"]
    # Why free models are in use, when they are.
    note: str | None
    groq_zdr_confirmed: bool
    # True when free models are in use and none may receive personal data yet.
    personal_work_waits: bool


class GroqZdr(BaseModel):
    confirmed: bool


@router.get("/api/model-settings")
def get_model_settings(user_id: UserId) -> ModelSettings:
    settings: Any = gateway.model_settings(user_id)
    until = settings["paid_unavailable_until"]
    if not gateway.has_keys(gateway.HAIKU):
        note: str | None = NO_KEY
    elif until is not None and until > datetime.now(UTC):
        note = settings["paid_unavailable_reason"]
    else:
        note = None
    free_ready = (
        gateway.has_keys(gateway.GROQ_PERSONAL) and settings["groq_zdr_confirmed"]
    ) or gateway.has_keys(gateway.CLOUDFLARE_PERSONAL)
    return ModelSettings(
        mode="free" if note else "paid",
        note=note,
        groq_zdr_confirmed=settings["groq_zdr_confirmed"],
        personal_work_waits=bool(note) and not free_ready,
    )


@router.put("/api/model-settings/groq-zdr")
def set_groq_zdr(new: GroqZdr, user_id: UserId) -> ModelSettings:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET groq_zdr_confirmed = %s WHERE id = %s", (new.confirmed, user_id)
        )
    return get_model_settings(user_id)
