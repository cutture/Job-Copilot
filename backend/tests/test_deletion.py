"""Deleting items and everything. Only model providers and Source responses are faked."""

from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot.api import app, current_user_id
from job_copilot.deletion import USER_TABLES
from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import apply, rated_match, run_worker, write
from tests.test_filter import prefer
from tests.test_rating import POSTING, answer, rate_posting, three_met
from tests.test_search import FakeBoards, boards, job, listed, search, watch

__all__ = ["boards"]  # A fixture the Source journey below uses.

USER = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")
RETRIEVAL_LINE = "Shipped retrieval systems to production"
RETRIEVAL_SENTENCE = "I shipped retrieval systems."


def rows(table: str, user_id: UUID = USER) -> int:
    with psycopg.connect(TEST_DB) as conn:
        found = conn.execute(f"SELECT count(*) FROM {table} WHERE user_id = %s", (user_id,))
        return int(found.fetchone()[0])  # type: ignore[index]


def ready_application(client: TestClient, provider: FakeProvider) -> tuple[str, str]:
    posting_id, ids = rated_match(client, provider)
    write(provider, ids)
    application_id: str = apply(client, posting_id)["id"]
    run_worker()
    return posting_id, application_id


def as_other_person() -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (OTHER,))
    app.dependency_overrides[current_user_id] = lambda: OTHER


def test_deleting_a_job_posting_deletes_its_match_application_and_pack(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, _ = ready_application(client, provider)

    assert client.delete(f"/api/job-postings/{posting_id}").status_code == 204

    assert client.get("/api/job-postings").json() == []
    assert client.get("/api/applications").json() == []
    for table in ("job_postings", "matches", "applications", "application_packs", "jobs"):
        assert rows(table) == 0, table
    assert client.delete(f"/api/job-postings/{posting_id}").status_code == 404


def test_a_deleted_source_posting_isnt_added_back(client: TestClient, boards: FakeBoards) -> None:
    prefer(client)
    watch(client, boards, "northwindlabs", "Northwind Labs")
    boards.jobs["northwindlabs"] = [job(1, 2), job(2, 3, "Data Engineer")]
    search(client)

    client.delete(f"/api/job-postings/{listed(client)['Data Engineer']['id']}")
    search(client)

    assert set(listed(client)) == {"Applied AI Engineer"}


def test_deleting_an_application_keeps_the_posting_and_the_spending_ledger(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, application_id = ready_application(client, provider)
    calls = rows("model_calls")

    assert client.delete(f"/api/applications/{application_id}").status_code == 204

    assert client.get(f"/api/applications/{application_id}").status_code == 404
    assert rows("application_packs") == 0
    # The Match stays, so the person can Apply again.
    [posting] = client.get("/api/job-postings").json()
    assert (posting["id"], posting["application_id"], posting["match"]["band"]) == (
        posting_id,
        None,
        "High",
    )
    # The ledger keeps every paid call, so the monthly cap stays true.
    assert rows("model_calls") == calls


def test_deleting_a_pack_keeps_the_application_which_can_get_a_new_pack(
    client: TestClient, provider: FakeProvider
) -> None:
    _, application_id = ready_application(client, provider)
    base = f"/api/applications/{application_id}"

    emptied = client.delete(f"{base}/pack")

    assert emptied.status_code == 200 and emptied.json()["pack"] is None
    assert client.get("/api/applications").json()[0]["status"] == "no_pack"
    assert client.get(f"{base}/resume.docx").status_code == 409
    assert client.delete(f"{base}/pack").status_code == 409

    assert client.post(f"{base}/pack").json()["pack"]["status"] == "generating"
    run_worker()
    assert client.get(base).json()["pack"]["status"] == "ready"
    assert client.post(f"{base}/pack").status_code == 409


def test_deleting_evidence_changes_unsubmitted_packs_and_marks_submitted_ones_and_matches(
    client: TestClient, provider: FakeProvider
) -> None:
    sent_posting, ids = rated_match(client, provider)
    write(provider, ids)
    sent = apply(client, sent_posting)["id"]
    draft_posting = rate_posting(
        client, provider, answer(*three_met(ids["retrieval"])), POSTING + " Second posting."
    )["id"]
    draft = apply(client, draft_posting)["id"]
    unapplied = rate_posting(
        client, provider, answer(*three_met(ids["retrieval"])), POSTING + " Third posting."
    )["id"]
    run_worker()
    for application_id in (sent, draft):
        client.put(f"/api/applications/{application_id}/review", json={"reviewed": True})
    client.post(f"/api/applications/{sent}/submitted")
    before = client.get(f"/api/applications/{sent}").json()["pack"]

    assert client.delete(f"/api/evidence/{ids['retrieval']}").status_code == 204

    # Unsubmitted: Claims resting only on that Evidence become Claims without Evidence.
    changed = client.get(f"/api/applications/{draft}").json()
    assert changed["reviewed"] is False
    assert changed["pack"]["resume"]["experience"][0]["lines"] == []
    moved = {r["text"]: r for r in changed["pack"]["removed_claims"]}
    assert moved[RETRIEVAL_LINE]["kind"] == moved[RETRIEVAL_SENTENCE]["kind"] == "evidence_deleted"
    assert moved[RETRIEVAL_LINE]["reason"] == "Its Evidence was deleted from your Profile."
    # Submitted: the Pack stays as it was sent, with that Evidence marked "source removed".
    kept = client.get(f"/api/applications/{sent}").json()
    assert kept["reviewed"] is True
    line = kept["pack"]["resume"]["experience"][0]["lines"][0]
    assert line["text"] == RETRIEVAL_LINE and line["evidence"][0]["source_removed"] is True
    assert kept["pack"]["removed_claims"] == before["removed_claims"]
    # Only the unapplied Match that cited it shows "Profile changed".
    matches = {p["id"]: p["match"] for p in client.get("/api/job-postings").json()}
    assert matches[unapplied]["profile_changed"] is True
    assert matches[sent_posting]["profile_changed"] is matches[draft_posting]["profile_changed"]
    assert matches[sent_posting]["profile_changed"] is False


def test_delete_everything_needs_delete_typed_and_leaves_no_row_for_the_person(
    client: TestClient, boards: FakeBoards, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    watch(client, boards, "northwindlabs", "Northwind Labs")
    search(client)
    posting_id, application_id = ready_application(client, provider)
    client.delete(f"/api/job-postings/{posting_id}")
    ready_application(client, provider)
    try:
        as_other_person()
        client.post("/api/job-postings", json={"text": "Data Engineer\nRemote"})
    finally:
        app.dependency_overrides.clear()
    theirs = rows("job_postings", OTHER)

    assert client.post("/api/delete-everything", json={"confirm": "delete"}).status_code == 422
    assert rows("job_postings") > 0

    report: dict[str, Any] = client.post(
        "/api/delete-everything", json={"confirm": "DELETE"}
    ).json()

    for table in USER_TABLES:
        assert rows(table) == 0, table
    assert rows("job_postings", OTHER) == theirs
    assert report["deleted"]["Applications"] == 1
    assert report["deleted"]["Evidence items"] == 6
    with psycopg.connect(TEST_DB) as conn:
        queued = conn.execute("SELECT count(*) FROM trace_deletions").fetchone()
    assert queued is not None and queued[0] > 0
    assert report["not_deleted"][0].startswith(f"{queued[0]} traces at Langfuse are queued")
    assert any("downloaded stay on your computer" in item for item in report["not_deleted"])


def test_every_table_with_a_persons_rows_is_deleted_by_delete_everything() -> None:
    with psycopg.connect(TEST_DB) as conn:
        found = conn.execute(
            """SELECT table_name FROM information_schema.columns
               WHERE column_name = 'user_id' AND table_schema = 'public'"""
        ).fetchall()
    # A new table holding a person's rows must join USER_TABLES.
    assert {row[0] for row in found} == set(USER_TABLES)


def test_another_persons_items_cant_be_deleted(client: TestClient, provider: FakeProvider) -> None:
    posting_id, application_id = ready_application(client, provider)
    try:
        as_other_person()
        assert client.delete(f"/api/job-postings/{posting_id}").status_code == 404
        assert client.delete(f"/api/applications/{application_id}").status_code == 404
        assert client.delete(f"/api/applications/{application_id}/pack").status_code == 404
        assert client.post(f"/api/applications/{application_id}/pack").status_code == 404
    finally:
        app.dependency_overrides.clear()
    assert rows("application_packs") == 1
