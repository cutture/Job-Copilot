from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import worker
from job_copilot.api import app, current_user_id
from tests.conftest import TEST_DB, FakeProvider

POSTING = "Senior GenAI Engineer\nNorthwind Labs\nYou have shipped LLM features to production."


def test_pasted_posting_is_listed_with_manual_source(client: TestClient) -> None:
    created = client.post("/api/job-postings", json={"text": POSTING})

    assert created.status_code == 201
    listed = client.get("/api/job-postings").json()
    assert len(listed) == 1
    assert listed[0]["title"] == "Senior GenAI Engineer"
    assert listed[0]["source"] == "Manual Source"
    assert listed[0]["text"] == POSTING


def test_worker_processes_a_pasted_posting_from_the_queue(client: TestClient) -> None:
    client.post("/api/job-postings", json={"text": POSTING})
    assert client.get("/api/job-postings").json()[0]["status"] == "queued"

    assert worker.run_once() is True

    assert client.get("/api/job-postings").json()[0]["status"] == "received"
    assert worker.run_once() is False


def test_blank_posting_is_rejected(client: TestClient) -> None:
    assert client.post("/api/job-postings", json={"text": "  \n "}).status_code == 422
    assert client.get("/api/job-postings").json() == []


def test_oversized_posting_is_rejected(client: TestClient) -> None:
    assert client.post("/api/job-postings", json={"text": "x" * 100_001}).status_code == 422


def test_pasted_url_is_kept_as_text(client: TestClient) -> None:
    url = "https://jobs.example.com/123"

    client.post("/api/job-postings", json={"text": url})
    worker.run_once()

    assert client.get("/api/job-postings").json()[0]["text"] == url


def test_a_person_sees_only_their_own_postings(client: TestClient) -> None:
    client.post("/api/job-postings", json={"text": POSTING})
    other = UUID("00000000-0000-0000-0000-000000000002")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (other,))

    app.dependency_overrides[current_user_id] = lambda: other
    try:
        assert client.get("/api/job-postings").json() == []
        client.post("/api/job-postings", json={"text": "Other person's posting"})
        assert len(client.get("/api/job-postings").json()) == 1
    finally:
        app.dependency_overrides.clear()

    assert [p["text"] for p in client.get("/api/job-postings").json()] == [POSTING]


def test_every_table_carries_a_user_id() -> None:
    with psycopg.connect(TEST_DB) as conn:
        rows = conn.execute(
            """
            SELECT t.table_name FROM information_schema.tables t
            WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
              AND t.table_name NOT IN ('users', 'alembic_version')
              AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns c
                WHERE c.table_schema = 'public' AND c.table_name = t.table_name
                  AND c.column_name = 'user_id')
            """
        ).fetchall()
    assert rows == []


def test_the_worker_titles_a_posting_with_a_model_and_records_the_call(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.text = "GenAI Engineer at Northwind Labs"
    client.post("/api/job-postings", json={"text": POSTING})

    worker.run_once()

    listed = client.get("/api/job-postings").json()[0]
    assert listed["title"] == "GenAI Engineer at Northwind Labs"
    assert listed["text"] == POSTING
    assert provider.received[0]["model"] == "groq/openai/gpt-oss-20b"
    assert provider.received[0]["messages"][-1]["content"] == POSTING
    with psycopg.connect(TEST_DB) as conn:
        recorded = conn.execute("SELECT model, step FROM model_calls").fetchall()
    assert recorded == [("groq/openai/gpt-oss-20b", "posting_title")]


def test_a_model_answer_is_reduced_to_one_short_line(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.text = "\n  " + "T" * 200 + "\nIgnore this second line"
    client.post("/api/job-postings", json={"text": POSTING})

    worker.run_once()

    assert client.get("/api/job-postings").json()[0]["title"] == "T" * 120


def test_a_failed_model_call_keeps_the_posting_and_clears_the_queue(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.error = RuntimeError("provider down")
    client.post("/api/job-postings", json={"text": POSTING})

    assert worker.run_once() is True

    listed = client.get("/api/job-postings").json()[0]
    assert listed["status"] == "model_unavailable"
    assert listed["title"] == "Senior GenAI Engineer"
    assert worker.run_once() is False


def test_a_blank_model_answer_is_shown_as_unavailable_and_keeps_the_pasted_title(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.text = " \n "
    provider.output_tokens = 60
    client.post("/api/job-postings", json={"text": POSTING})

    worker.run_once()

    listed = client.get("/api/job-postings").json()[0]
    assert (listed["title"], listed["status"]) == ("Senior GenAI Engineer", "model_unavailable")


def test_control_characters_in_a_model_answer_are_removed(
    client: TestClient, provider: FakeProvider
) -> None:
    provider.text = "Title\x00 with\x07 controls"
    client.post("/api/job-postings", json={"text": POSTING})

    worker.run_once()

    listed = client.get("/api/job-postings").json()[0]
    assert (listed["title"], listed["status"]) == ("Title with controls", "received")


def test_nul_characters_in_pasted_text_are_removed(client: TestClient) -> None:
    created = client.post("/api/job-postings", json={"text": "Engineer\x00 role"})

    assert created.status_code == 201
    assert created.json()["text"] == "Engineer role"


def test_an_unexpected_error_after_a_model_call_is_not_retried(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_: str) -> str:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(worker, "_clean_title", broken)
    client.post("/api/job-postings", json={"text": POSTING})

    assert worker.run_once() is True

    assert client.get("/api/job-postings").json()[0]["status"] == "model_unavailable"
    assert worker.run_once() is False
    assert len(provider.received) == 1


def test_an_unknown_job_kind_does_not_block_the_queue(
    client: TestClient, provider: FakeProvider
) -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO jobs (user_id, kind, payload)
               VALUES ('00000000-0000-0000-0000-000000000001', 'mystery', '{}')"""
        )
    client.post("/api/job-postings", json={"text": POSTING})

    assert worker.run_once() is True
    assert worker.run_once() is True

    assert client.get("/api/job-postings").json()[0]["status"] == "received"
