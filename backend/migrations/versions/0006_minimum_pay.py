"""Minimum Pay for each currency, replacing the single minimum salary."""

from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    # A minimum saved without a currency is kept, and the Profile asks for its currency.
    op.execute(
        """
        ALTER TABLE profiles ADD COLUMN min_pay jsonb NOT NULL DEFAULT '[]';
        UPDATE profiles
            SET min_pay = jsonb_build_array(jsonb_build_object(
                'currency', min_salary_currency, 'yearly', min_salary, 'hourly', null))
            WHERE min_salary > 0;
        ALTER TABLE profiles DROP COLUMN min_salary, DROP COLUMN min_salary_currency;
        """
    )
