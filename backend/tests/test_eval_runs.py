"""Daily Eval Runs, the Eval Runs page, and the warnings a failing run turns on."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import eval_runs, evals, worker
from job_copilot.api import app
from job_copilot.db import EVAL_USER_ID
from job_copilot.filter import FILTER_MODEL
from tests.conftest import TEST_DB, FakeProvider
from tests.test_application_pack import apply, rated_match, run_worker
from tests.test_deletion import as_other_person
from tests.test_evals import LOADED, OWNER, cases_file
from tests.test_filter import facts
from tests.test_my_sections import ready_pack, write_sections


def filter_run(provider: FakeProvider, tmp_path: Path, passes: bool, checked: bool = True) -> int:
    """An Eval Run of one Filter case, which the fake Filter answer passes or fails."""
    # The case's remote posting passes; read as on-site in Berlin, it's wrongly set aside.
    provider.answers = {
        FILTER_MODEL: facts()
        if passes
        else facts(work_arrangement="on_site", locations=["Berlin, Germany"])
    }
    unchecked = () if checked else ("filter-remote-pay-fits",)
    return evals.run(OWNER, cases_file(tmp_path, "filter-remote-pay-fits", unchecked=unchecked))


class Counts(NamedTuple):
    runs: int
    case_jobs: int


@pytest.fixture(autouse=True)
def daily_runs_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about the daily run; Challenger runs have their own tests."""
    monkeypatch.setattr(eval_runs, "CHALLENGERS", ())


def counts() -> Counts:
    """Eval Runs started, and Eval Case jobs still queued."""
    with psycopg.connect(TEST_DB) as conn:
        row = conn.execute(
            """SELECT (SELECT count(*) FROM eval_runs),
                      (SELECT count(*) FROM jobs WHERE kind = %s)""",
            (eval_runs.EVAL_CASE_JOB,),
        ).fetchone()
    assert row is not None
    return Counts(runs=int(row[0]), case_jobs=int(row[1]))


def queue_todays_run() -> None:
    worker.schedule_daily_evals(datetime.now(UTC).replace(hour=23))


def statuses(client: TestClient) -> list[tuple[str, str]]:
    [run] = client.get("/api/eval-runs").json()
    assert run["finished_at"] is not None
    return [
        (r["status"], r["reason"])
        for r in client.get(f"/api/eval-runs/{run['id']}").json()["results"]
    ]


def test_the_set_has_4_filter_8_scoring_8_pack_and_4_injection_cases() -> None:
    areas = [case["area"] for case in LOADED["cases"]]

    assert {area: areas.count(area) for area in set(areas)} == {
        "filter": 4,
        "scoring": 8,
        "pack": 8,
        "injection": 4,
    }
    assert len({case["id"] for case in LOADED["cases"]}) == 24


def test_an_eval_run_is_queued_once_a_day_after_its_hour_as_one_job_per_case(
    provider: FakeProvider, tmp_path: Path
) -> None:
    morning = datetime(2026, 11, 8, worker.EVAL_HOUR_UTC - 1, tzinfo=UTC)
    later = datetime(2026, 11, 8, worker.EVAL_HOUR_UTC, tzinfo=UTC)

    worker.schedule_daily_evals(morning)
    assert counts() == (0, 0)
    worker.schedule_daily_evals(later)
    # As after a restart: the run is already queued, so nothing more is.
    worker.schedule_daily_evals(later)
    assert counts() == (1, 24)


def test_no_second_run_is_queued_on_a_day_that_already_had_one(
    provider: FakeProvider, tmp_path: Path
) -> None:
    filter_run(provider, tmp_path, passes=True)

    queue_todays_run()

    assert counts() == (1, 0)


def test_the_queued_run_runs_every_case_and_finishes_after_the_last(
    client: TestClient, provider: FakeProvider
) -> None:
    queue_todays_run()

    worker.run_once()
    [running] = client.get("/api/eval-runs").json()
    assert running["finished_at"] is None
    assert client.get("/api/evals/status").json()["failing"] is False

    run_worker()

    [run] = client.get("/api/eval-runs").json()
    assert run["finished_at"] is not None
    assert run["passed"] + run["failed"] + run["did_not_run"] == 24


def test_a_pack_queued_mid_run_goes_before_the_next_eval_case(
    client: TestClient, provider: FakeProvider
) -> None:
    posting_id, ids = rated_match(client, provider)
    write_sections(provider, ids)
    queue_todays_run()
    worker.run_once()

    application = apply(client, posting_id)
    worker.run_once()

    pack = client.get(f"/api/applications/{application['id']}").json()["pack"]
    assert pack["status"] == "ready"
    assert counts() == (1, 23)


def test_a_case_the_worker_was_running_when_it_died_shows_as_not_run(
    client: TestClient, provider: FakeProvider
) -> None:
    queue_todays_run()
    while counts().case_jobs > 1:
        worker.run_once()
    # The worker claimed the last case, which deletes its job, and then died.
    with psycopg.connect(TEST_DB) as conn:
        conn.execute("DELETE FROM jobs WHERE kind = %s", (eval_runs.EVAL_CASE_JOB,))

    worker.finish_interrupted_evals()

    results = statuses(client)
    assert len(results) == 24
    assert results.count(("did_not_run", "The worker stopped during this case")) == 1


def test_a_case_whose_result_cant_be_saved_is_still_recorded_as_failed(
    client: TestClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def cant_save(*args: object) -> None:
        raise psycopg.OperationalError("lost connection")

    monkeypatch.setattr(evals, "_record", cant_save)
    queue_todays_run()

    run_worker()

    assert set(statuses(client)) == {("failed", "The worker couldn't record this case")}


def test_queued_cases_stop_at_the_eval_cap(client: TestClient, provider: FakeProvider) -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE users SET monthly_cap_usd = 0 WHERE id = %s", (EVAL_USER_ID,))
    try:
        queue_todays_run()
        run_worker()
    finally:
        with psycopg.connect(TEST_DB, autocommit=True) as conn:
            conn.execute("UPDATE users SET monthly_cap_usd = 3 WHERE id = %s", (EVAL_USER_ID,))

    # Filter's free model isn't capped, so only the 19 cases that reach a paid step stop.
    results = statuses(client)
    assert len(results) == 24
    assert results.count(("did_not_run", "Did not run: the eval budget is used up")) == 19


def test_a_case_that_crashes_fails_alone_and_the_run_still_finishes(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    # A case with no posting can't come from the cases file honestly; it stands in for any
    # step that crashes, which no honest input can be made to do on purpose.
    broken = tmp_path / "cases.json"
    good = cases_file(tmp_path, "filter-on-site-elsewhere")
    loaded = json.loads(good.read_text(encoding="utf-8"))
    crashing = {**loaded["cases"][0], "id": "crashing-case"}
    del crashing["posting"]
    broken.write_text(json.dumps({**loaded, "cases": [crashing, loaded["cases"][0]]}))
    provider.answers = {FILTER_MODEL: facts(work_arrangement="on_site", locations=["Berlin"])}

    run_id = evals.run(OWNER, broken)

    run = client.get(f"/api/eval-runs/{run_id}").json()
    assert run["finished_at"] is not None
    assert [(r["case_id"], r["status"]) for r in run["results"]] == [
        ("crashing-case", "failed"),
        ("filter-on-site-elsewhere", "passed"),
    ]
    assert run["results"][0]["reason"] == "The case crashed (KeyError)"


def test_the_eval_runs_page_shows_each_failure_with_its_reason_and_area_to_fix(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    filter_run(provider, tmp_path, passes=True)
    failing = filter_run(provider, tmp_path, passes=False)

    runs = client.get("/api/eval-runs").json()
    results = client.get(f"/api/eval-runs/{failing}").json()["results"]

    assert [(r["id"], r["passed"], r["failed"]) for r in runs][:2] == [
        (failing, 0, 1),
        (runs[1]["id"], 1, 0),
    ]
    [result] = results
    assert result["case_id"] == "filter-remote-pay-fits"
    assert result["reason"].startswith("Filter set it aside: On-site")
    assert result["fix_area"].startswith("Filter")


def test_another_persons_eval_runs_arent_shown(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    run_id = filter_run(provider, tmp_path, passes=False)
    try:
        as_other_person()
        assert client.get("/api/eval-runs").json() == []
        assert client.get(f"/api/eval-runs/{run_id}").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_a_failing_run_turns_on_the_banner_and_extra_care_until_a_run_passes(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    filter_run(provider, tmp_path, passes=False)
    assert client.get("/api/evals/status").json()["failing"] is True

    pack = ready_pack(client, provider)
    assert pack["extra_care"] is True

    filter_run(provider, tmp_path, passes=True)
    assert client.get("/api/evals/status").json()["failing"] is False
    assert client.get(f"/api/applications/{pack['id']}").json()["pack"]["extra_care"] is False


def test_a_failure_in_a_case_whose_labels_arent_checked_doesnt_warn(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    filter_run(provider, tmp_path, passes=False, checked=False)

    assert client.get("/api/evals/status").json()["failing"] is False


def test_an_injection_case_labelled_with_a_filter_result_goes_through_filter(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    # The planted note talks the model into "remote"; the posting's own words still say on-site.
    provider.answers = {FILTER_MODEL: facts(work_arrangement="remote")}

    run_id = evals.run(OWNER, cases_file(tmp_path, "injection-filter-remote"))

    [result] = client.get(f"/api/eval-runs/{run_id}").json()["results"]
    assert (result["status"], result["reason"]) == ("passed", "Matches its labels")
