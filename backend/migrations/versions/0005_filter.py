"""Filter results on Job Postings, and the currency of the person's minimum salary."""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE job_postings
            ADD COLUMN posting_type text CHECK (posting_type IN ('employment', 'freelance')),
            ADD COLUMN filter_reason text,
            ADD COLUMN salary_note text;
        ALTER TABLE profiles ADD COLUMN min_salary_currency text;
        """
    )
