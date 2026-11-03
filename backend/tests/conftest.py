import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from job_copilot import gateway

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:test@127.0.0.1:55432/job_copilot_test"
)
os.environ["DATABASE_URL"] = TEST_DB

BACKEND = Path(__file__).resolve().parent.parent

real_call_provider = gateway.call_provider
real_send_trace = gateway.send_trace


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(name, raising=False)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("TRUNCATE jobs, job_postings, model_calls, evidence, profiles")


@dataclass
class FakeProvider:
    """Stands in for model providers and records everything it receives."""

    text: str = "Fake model answer"
    input_tokens: int = 10
    output_tokens: int = 5
    error: Exception | None = None
    received: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture(autouse=True)
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    fake = FakeProvider()

    def call(model: str, messages: list[dict[str, str]], max_tokens: int) -> gateway.ProviderAnswer:
        fake.received.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        if fake.error:
            raise fake.error
        return gateway.ProviderAnswer(fake.text, fake.input_tokens, fake.output_tokens)

    monkeypatch.setattr(gateway, "call_provider", call)
    return fake


@pytest.fixture(autouse=True)
def traces(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def record(settings: gateway.TraceSettings, event: dict[str, Any]) -> None:
        sent.append({"host": settings.host, **event})

    monkeypatch.setattr(gateway, "send_trace", record)
    return sent


@pytest.fixture
def client() -> Iterator[TestClient]:
    from job_copilot.api import app

    with TestClient(app) as test_client:
        yield test_client
