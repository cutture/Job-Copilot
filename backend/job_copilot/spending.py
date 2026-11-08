"""Spending: paid API use by month against the person's cap, evals included.

The spending ledger is model_calls. Every paid call is recorded there with its cost, whatever
the provider or billing source, and the gateway checks the same totals before each call.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from job_copilot.db import EVAL_USER_ID, UserId, connect
from job_copilot.gateway import MONTH_START, cap_and_spent, spenders

router = APIRouter()

WARN_AT = Decimal("0.8")
# Months of spending shown: the spec keeps the ledger 13 months, and clean-up comes with #32.
MONTHS_SHOWN = 13
Level = Literal["ok", "warning", "reached"]
MAX_CAP_USD = 1000


class MonthSpending(BaseModel):
    month: datetime
    spent_usd: Decimal
    # Part of spent_usd, from Eval Runs.
    evals_usd: Decimal


class Spending(BaseModel):
    spent_usd: Decimal
    evals_usd: Decimal
    cap_usd: Decimal
    # Evals stop at their own cap first, inside the person's.
    eval_cap_usd: Decimal | None
    level: Level
    warning: str | None
    months: list[MonthSpending]


class NewCap(BaseModel):
    monthly_cap_usd: Decimal = Field(gt=0, le=MAX_CAP_USD, decimal_places=2)


def _warning(spent: Decimal, cap: Decimal) -> tuple[Level, str | None]:
    if spent >= cap:
        return "reached", (
            f"You've reached this month's ${cap:.2f} cap. Paid AI work, such as ratings, reading "
            "your resume and Application Packs, stops until the 1st or until you raise the cap "
            "on the Settings page. Reading new postings keeps working."
        )
    if spent >= WARN_AT * cap:
        return "warning", (
            f"You've used 80% of this month's ${cap:.2f} cap: ${spent:.2f} so far. Raise the cap "
            "on the Settings page if you need more."
        )
    return "ok", None


@router.get("/api/spending")
def get_spending(user_id: UserId) -> Spending:
    with connect() as conn:
        cap, spent = cap_and_spent(conn, user_id)
        eval_cap = (
            cap_and_spent(conn, EVAL_USER_ID)[0] if EVAL_USER_ID in spenders(user_id) else None
        )
        rows: Any = conn.execute(
            f"""SELECT date_trunc('month', created_at AT TIME ZONE 'UTC') AS month,
                       SUM(cost_usd) AS spent_usd,
                       COALESCE(SUM(cost_usd) FILTER (WHERE user_id = %s), 0) AS evals_usd
                FROM model_calls
                WHERE user_id = ANY(%s)
                  AND created_at >= {MONTH_START} - %s * interval '1 month'
                GROUP BY 1 ORDER BY 1 DESC""",
            (EVAL_USER_ID, list(spenders(user_id)), MONTHS_SHOWN - 1),
        ).fetchall()
        this_month: Any = conn.execute(
            f"SELECT date_trunc('month', {MONTH_START} AT TIME ZONE 'UTC') AS month"
        ).fetchone()
    months = [MonthSpending(**row) for row in rows]
    if not months or months[0].month != this_month["month"]:
        months.insert(
            0, MonthSpending(month=this_month["month"], spent_usd=Decimal(0), evals_usd=Decimal(0))
        )
    level, warning = _warning(spent, cap)
    return Spending(
        spent_usd=spent,
        evals_usd=months[0].evals_usd,
        cap_usd=cap,
        eval_cap_usd=eval_cap,
        level=level,
        warning=warning,
        months=months,
    )


@router.put("/api/spending/cap")
def set_cap(new: NewCap, user_id: UserId) -> Spending:
    with connect() as conn:
        conn.execute(
            "UPDATE users SET monthly_cap_usd = %s WHERE id = %s", (new.monthly_cap_usd, user_id)
        )
    return get_spending(user_id)
