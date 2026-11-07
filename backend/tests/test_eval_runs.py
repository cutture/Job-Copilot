"""Daily Eval Runs, the Eval Runs page, and the warnings a failing run turns on."""

import json
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

from job_copilot import evals, worker
from job_copilot.api import app
from job_copilot.filter import FILTER_MODEL
from tests.conftest import TEST_DB, FakeProvider
from tests.test_deletion import as_other_person
from tests.test_evals import LOADED, OWNER, cases_file
from tests.test_filter import facts
from tests.test_my_sections import ready_pack


def filter_run(provider: FakeProvider, tmp_path: Path, passes: bool, checked: bool = True) -> int:
    """An Eval Run of one Filter case, which the fake Filter answer passes or fails."""
    provider.answers = {
        FILTER_MODEL: facts(work_arrangement="on_site", locations=["Berlin, Germany"])
        if passes
        else facts()
    }
    unchecked = () if checked else ("filter-on-site-elsewhere",)
    return evals.run(OWNER, cases_file(tmp_path, "filter-on-site-elsewhere", unchecked=unchecked))


def queued_eval_runs() -> int:
    with psycopg.connect(TEST_DB) as conn:
        row = conn.execute("SELECT count(*) FROM jobs WHERE kind = 'eval_run'").fetchone()
    return int(row[0]) if row else 0


def test_the_set_has_4_filter_8_scoring_8_pack_and_4_injection_cases() -> None:
    areas = [case["area"] for case in LOADED["cases"]]

    assert {area: areas.count(area) for area in set(areas)} == {
        "filter": 4,
        "scoring": 8,
        "pack": 8,
        "injection": 4,
    }
    assert len({case["id"] for case in LOADED["cases"]}) == 24


def test_an_eval_run_is_queued_once_a_day_after_its_hour(
    provider: FakeProvider, tmp_path: Path
) -> None:
    morning = datetime(2026, 11, 8, worker.EVAL_HOUR_UTC - 1, tzinfo=UTC)
    later = datetime(2026, 11, 8, worker.EVAL_HOUR_UTC, tzinfo=UTC)

    worker.schedule_daily_evals(morning)
    assert queued_eval_runs() == 0
    worker.schedule_daily_evals(later)
    worker.schedule_daily_evals(later)
    assert queued_eval_runs() == 1


def test_no_second_run_is_queued_on_a_day_that_already_had_one(
    provider: FakeProvider, tmp_path: Path
) -> None:
    filter_run(provider, tmp_path, passes=True)

    worker.schedule_daily_evals(datetime.now(UTC).replace(hour=23))

    assert queued_eval_runs() == 0


def test_the_queued_run_runs_every_case_from_the_worker(provider: FakeProvider) -> None:
    worker.schedule_daily_evals(datetime.now(UTC).replace(hour=23))

    worker.run_once()

    with psycopg.connect(TEST_DB) as conn:
        runs = conn.execute("SELECT id, finished_at FROM eval_runs").fetchall()
        results = conn.execute("SELECT count(*) FROM eval_results").fetchone()
    assert len(runs) == 1 and runs[0][1] is not None
    assert results == (24,)


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
    assert result["case_id"] == "filter-on-site-elsewhere"
    assert result["reason"] == "Filter let it through"
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
