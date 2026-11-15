"""Automatic clean-up on the spec's retention schedule, the notice before it, and trace deletion."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import retention, worker
from job_copilot.db import EVAL_USER_ID, SEEDED_USER_ID
from tests.conftest import TEST_DB, FakeProvider
from tests.test_evals import OWNER, cases_file
from tests.test_filter import facts, filter_posting
from tests.test_my_sections import ready_pack


def today() -> date:
    """Today in UTC, the day the database counts in."""
    return datetime.now(UTC).date()


def age(
    table: str, column: str, days: int, where: str = "true", params: tuple[Any, ...] = ()
) -> None:
    """Move a timestamp back, as if that many days had passed."""
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            f"UPDATE {table} SET {column} = now() - %s * interval '1 day' WHERE {where}",
            (days, *params),
        )


def count(sql: str, params: tuple[Any, ...] = ()) -> int:
    with psycopg.connect(TEST_DB) as conn:
        row = conn.execute(sql, params).fetchone()
    assert row is not None
    return int(row[0])


def posting_ids(client: TestClient) -> set[str]:
    return {p["id"] for p in client.get("/api/job-postings").json()}


def filtered(client: TestClient, provider: FakeProvider) -> dict[str, Any]:
    return filter_posting(client, provider, facts(work_arrangement="on_site", locations=["Berlin"]))


def test_filtered_postings_go_after_30_days_with_a_notice_before(
    client: TestClient, provider: FakeProvider
) -> None:
    old, recent = filtered(client, provider), filtered(client, provider)
    assert old["status"] == "filtered"
    age("job_postings", "created_at", 31, "id = %s", (old["id"],))

    retention.clean_up()

    assert posting_ids(client) == {recent["id"]}
    [shown] = client.get("/api/job-postings").json()
    assert shown["deletes_on"] == str(today() + timedelta(days=30))


def test_a_posting_with_no_application_goes_90_days_after_it_expires(
    client: TestClient, provider: FakeProvider
) -> None:
    gone = filter_posting(client, provider, facts())
    with_application = ready_pack(client, provider)
    age("job_postings", "expired_at", 91)

    retention.clean_up()

    assert count("SELECT count(*) FROM job_postings WHERE id = %s", (gone["id"],)) == 0
    assert client.get(f"/api/applications/{with_application['id']}").status_code == 200


def test_a_pack_never_submitted_goes_90_days_after_it_was_last_opened(
    client: TestClient, provider: FakeProvider
) -> None:
    ready_pack(client, provider)
    age("applications", "opened_at", 84)
    [row] = client.get("/api/applications").json()
    assert row["deletes_on"] == str(today() + timedelta(days=6))

    age("applications", "opened_at", 91)
    retention.clean_up()

    [row] = client.get("/api/applications").json()
    assert row["status"] == "no_pack"
    assert row["deletes_on"] is None


def test_opening_a_pack_keeps_it_another_90_days(
    client: TestClient, provider: FakeProvider
) -> None:
    pack = ready_pack(client, provider)
    age("applications", "opened_at", 89)

    client.get(f"/api/applications/{pack['id']}")
    age("applications", "opened_at", 2, "opened_at > now() - interval '1 hour'")
    retention.clean_up()

    assert client.get(f"/api/applications/{pack['id']}").json()["pack"]["status"] == "ready"


def test_a_submitted_application_keeps_only_the_version_sent_after_30_days(
    client: TestClient, provider: FakeProvider
) -> None:
    pack = ready_pack(client, provider)
    base = f"/api/applications/{pack['id']}"
    # An earlier version, as Change Requests will make; nothing else makes two versions yet.
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO application_packs (user_id, application_id, version, status, resume,
                                              cover_letter, removed_claims, model)
               SELECT user_id, application_id, 0, status, resume, cover_letter, removed_claims,
                      model
               FROM application_packs WHERE application_id = %s""",
            (pack["id"],),
        )
    client.put(f"{base}/review", json={"reviewed": True})
    client.post(f"{base}/submitted")
    versions = "SELECT count(*) FROM application_packs WHERE application_id = %s"
    assert count(versions, (pack["id"],)) == 2

    age("applications", "submitted_at", 29)
    retention.clean_up()
    assert count(versions, (pack["id"],)) == 2

    age("applications", "submitted_at", 31)
    age("applications", "opened_at", 400)
    retention.clean_up()
    sent = client.get(base).json()["pack"]
    assert count(versions, (pack["id"],)) == 1
    assert (sent["status"], sent["version"]) == ("ready", 1)


def test_the_version_sent_stays_even_when_a_newer_one_exists(
    client: TestClient, provider: FakeProvider
) -> None:
    pack = ready_pack(client, provider)
    base = f"/api/applications/{pack['id']}"
    client.put(f"{base}/review", json={"reviewed": True})
    client.post(f"{base}/submitted")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO application_packs (user_id, application_id, version, status, resume,
                                              cover_letter, removed_claims, model)
               SELECT user_id, application_id, 2, status, resume, cover_letter, removed_claims,
                      model
               FROM application_packs WHERE application_id = %s""",
            (pack["id"],),
        )
    age("applications", "submitted_at", 31)

    retention.clean_up()

    with psycopg.connect(TEST_DB) as conn:
        kept = conn.execute(
            "SELECT version FROM application_packs WHERE application_id = %s", (pack["id"],)
        ).fetchall()
    assert kept == [(1,)]


def test_eval_runs_go_after_12_months_and_the_ledger_after_13_with_its_traces_queued(
    client: TestClient, provider: FakeProvider, tmp_path: Any
) -> None:
    from job_copilot import evals

    old_run = evals.run(OWNER, cases_file(tmp_path, "filter-remote-pay-fits"))
    new_run = evals.run(OWNER, cases_file(tmp_path, "filter-remote-pay-fits"))
    age("eval_runs", "started_at", 366, "id = %s", (old_run,))
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        for user, trace, days in [(SEEDED_USER_ID, "a" * 32, 400), (EVAL_USER_ID, "b" * 32, 420)]:
            conn.execute(
                """INSERT INTO model_calls (user_id, model, step, input_tokens, output_tokens,
                                            cost_usd, trace_id, created_at)
                   VALUES (%s, 'seed', 'seed', 0, 0, 0, %s, now() - %s * interval '1 day')""",
                (user, trace, days),
            )

    retention.clean_up()

    assert [r["id"] for r in client.get("/api/eval-runs").json()] == [new_run]
    assert (
        count("SELECT count(*) FROM model_calls WHERE created_at < now() - interval '1 year'") == 0
    )
    assert count("SELECT count(*) FROM trace_deletions WHERE sent_at IS NULL") == 2


def queue_traces(n: int) -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DELETE FROM trace_deletions")
        for i in range(n):
            conn.execute("INSERT INTO trace_deletions (trace_id) VALUES (%s)", (f"{i:032x}",))


def tracing_on(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    deleted: list[str] = []

    def delete(url: str, **kwargs: Any) -> httpx.Response:
        deleted.append(url.rsplit("/", 1)[1])
        return httpx.Response(200, request=httpx.Request("DELETE", url))

    monkeypatch.setattr(httpx, "delete", delete)
    return deleted


def test_queued_traces_are_deleted_at_langfuse_at_most_50_a_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted = tracing_on(monkeypatch)
    queue_traces(60)

    retention.send_trace_deletions()
    retention.send_trace_deletions()

    assert len(deleted) == 50
    assert count("SELECT count(*) FROM trace_deletions WHERE sent_at IS NULL") == 10


def test_traces_wait_while_tracing_isnt_set_up(monkeypatch: pytest.MonkeyPatch) -> None:
    queue_traces(3)

    retention.send_trace_deletions()

    assert count("SELECT count(*) FROM trace_deletions WHERE sent_at IS NULL") == 3


def test_a_failed_trace_deletion_stays_queued(monkeypatch: pytest.MonkeyPatch) -> None:
    tracing_on(monkeypatch)

    def refuse(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(500, request=httpx.Request("DELETE", url))

    monkeypatch.setattr(httpx, "delete", refuse)
    queue_traces(2)

    retention.send_trace_deletions()

    assert count("SELECT count(*) FROM trace_deletions WHERE sent_at IS NULL") == 2


def test_failed_trace_deletions_count_towards_the_50_a_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracing_on(monkeypatch)
    tried: list[str] = []

    def refuse(url: str, **kwargs: Any) -> httpx.Response:
        tried.append(url)
        return httpx.Response(500, request=httpx.Request("DELETE", url))

    monkeypatch.setattr(httpx, "delete", refuse)
    queue_traces(60)

    retention.send_trace_deletions()
    retention.send_trace_deletions()

    assert len(tried) == 50


def test_the_worker_cleans_up_once_a_day(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "_cleaned_on", None)
    today = datetime.now(UTC)
    first = filtered(client, provider)
    age("job_postings", "created_at", 31, "id = %s", (first["id"],))

    worker.daily_clean_up(today)
    assert first["id"] not in posting_ids(client)

    second = filtered(client, provider)
    age("job_postings", "created_at", 31, "id = %s", (second["id"],))
    worker.daily_clean_up(today)
    assert second["id"] in posting_ids(client)

    worker.daily_clean_up(today + timedelta(days=1))
    assert second["id"] not in posting_ids(client)


def test_docker_rotates_every_services_logs() -> None:
    compose = (Path(__file__).parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    services = compose.split("\nservices:\n", 1)[1].split("\nvolumes:", 1)[0]
    names = [line[2:-1] for line in services.splitlines() if line[:2] == "  " and line[2] != " "]

    assert names == ["db", "api", "worker", "web"]
    assert services.count("logging: *rotated-logs") == len(names)
    assert "max-size:" in compose
