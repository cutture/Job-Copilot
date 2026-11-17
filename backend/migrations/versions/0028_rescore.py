"""Rescore: what a rating needs to judge a Match again without reading the posting again."""

from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade() -> None:
    op.execute(
        """
        -- The posting's seniority statement (level, quote, firm minimum), so a Rescore can
        -- judge seniority against the Profile again; NULL for Matches rated before it was kept.
        ALTER TABLE matches ADD COLUMN seniority jsonb;
        -- The Band before the latest Rescore, so the person sees what changed.
        ALTER TABLE matches ADD COLUMN previous_band text;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE matches DROP COLUMN previous_band, DROP COLUMN seniority;")
