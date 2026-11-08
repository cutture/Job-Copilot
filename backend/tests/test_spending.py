"""Spending against the monthly cap, evals included. Only model providers are faked."""

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from job_copilot import gateway
from job_copilot.api import app
from job_copilot.db import EVAL_USER_ID, SEEDED_USER_ID
from job_copilot.gateway import CapReached, DataClass
from tests.conftest import TEST_DB, FakeProvider
from tests.test_deletion import as_other_person

HAIKU = "anthropic/claude-haiku-5-5"


def spend(amount: str, user: UUID = SEEDED_USER_ID, when: str = "now()") -> None:
    # Ledger entries are made by paid calls; seeding them sets a month's spending directly,
    # including months before this one, which no call made now could record.
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(
            f"""INSERT INTO model_calls
                (user_id, model, step, input_tokens, output_tokens, cost_usd, created_at)
                VALUES (%s, 'seed', 'seed', 0, 0, %s, {when})""",
            (user, Decimal(amount)),
        )


def ask(user: UUID) -> Any:
    return gateway.complete(
        user_id=user,
        model=HAIKU,
        data_class=DataClass.POSTING,
        step="test",
        messages=[{"role": "user", "content": "hello"}],
        max_output_tokens=100,
    )


def spending(client: TestClient) -> Any:
    response = client.get("/api/spending")
    assert response.status_code == 200
    return response.json()


def test_this_months_spending_includes_evals_against_the_cap(client: TestClient) -> None:
    spend("2.50")
    spend("1.25", EVAL_USER_ID)

    shown = spending(client)

    assert Decimal(shown["spent_usd"]) == Decimal("3.75")
    assert Decimal(shown["evals_usd"]) == Decimal("1.25")
    assert Decimal(shown["cap_usd"]) == Decimal("10")
    assert Decimal(shown["eval_cap_usd"]) == Decimal("3")
    assert (shown["level"], shown["warning"]) == ("ok", None)


def test_spending_shows_by_month_and_last_months_doesnt_count_now(client: TestClient) -> None:
    spend("4.00", when="date_trunc('month', now()) - interval '10 days'")
    spend("0.50", EVAL_USER_ID, when="date_trunc('month', now()) - interval '10 days'")
    spend("1.00")

    shown = spending(client)

    assert Decimal(shown["spent_usd"]) == Decimal("1.00")
    this, last = shown["months"][:2]
    assert (Decimal(this["spent_usd"]), Decimal(this["evals_usd"])) == (Decimal(1), Decimal(0))
    assert (Decimal(last["spent_usd"]), Decimal(last["evals_usd"])) == (
        Decimal("4.50"),
        Decimal("0.50"),
    )
    assert last["month"] < this["month"]


@pytest.mark.parametrize(
    ("amount", "level", "warning"),
    [
        ("7.99", "ok", None),
        ("8.00", "warning", "You've used 80% of this month's $10.00 cap"),
        ("10.00", "reached", "You've reached this month's $10.00 cap"),
    ],
)
def test_warnings_show_at_80_percent_and_at_the_cap(
    client: TestClient, amount: str, level: str, warning: str | None
) -> None:
    spend(amount)

    shown = spending(client)

    assert shown["level"] == level
    assert shown["warning"] == warning or warning in (shown["warning"] or "")


def test_the_owners_cap_counts_eval_spending(provider: FakeProvider) -> None:
    spend("7.50")
    spend("2.50", EVAL_USER_ID)

    with pytest.raises(CapReached):
        ask(SEEDED_USER_ID)

    assert provider.received == []


def test_evals_stop_at_the_owners_cap_even_under_their_own(provider: FakeProvider) -> None:
    spend("9.80")
    spend("0.20", EVAL_USER_ID)

    with pytest.raises(CapReached):
        ask(EVAL_USER_ID)


def test_the_cap_can_be_changed_within_limits(client: TestClient, provider: FakeProvider) -> None:
    spend("10.00")
    try:
        assert client.put("/api/spending/cap", json={"monthly_cap_usd": 20}).status_code == 200
        assert Decimal(spending(client)["cap_usd"]) == 20
        ask(SEEDED_USER_ID)
        for bad in (0, -5, 1001, "lots"):
            assert client.put("/api/spending/cap", json={"monthly_cap_usd": bad}).status_code == 422
    finally:
        client.put("/api/spending/cap", json={"monthly_cap_usd": 10})


def test_another_persons_spending_isnt_shown(client: TestClient) -> None:
    spend("6.00")
    try:
        as_other_person()
        shown = spending(client)
        assert Decimal(shown["spent_usd"]) == 0
        assert Decimal(shown["evals_usd"]) == 0
    finally:
        app.dependency_overrides.clear()


def test_delete_everything_keeps_eval_spending_unless_eval_runs_go_too(
    client: TestClient,
) -> None:
    spend("2.00")
    spend("1.00", EVAL_USER_ID)

    kept = client.post("/api/delete-everything", json={"confirm": "DELETE"}).json()

    assert Decimal(spending(client)["spent_usd"]) == Decimal("1.00")
    assert "apart from Eval Runs' spending" in kept["notes"][0]

    gone = client.post(
        "/api/delete-everything", json={"confirm": "DELETE", "include_eval_runs": True}
    ).json()

    assert Decimal(spending(client)["spent_usd"]) == 0
    assert gone["notes"] == [
        "The spending ledger is deleted too, so this month's spending starts again from $0."
    ]
