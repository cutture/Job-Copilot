"""Tracked Scores: what each Eval Case counted, and whether its new labels are checked."""

from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade() -> None:
    op.execute(
        """
        -- The counts a case adds to its run's Tracked Scores; null for a case that didn't run.
        ALTER TABLE eval_results ADD COLUMN scores jsonb;
        -- Labels added for Tracked Scores count only once the owner checks them.
        ALTER TABLE eval_results ADD COLUMN scores_checked boolean NOT NULL DEFAULT true;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE eval_results DROP COLUMN scores;
        ALTER TABLE eval_results DROP COLUMN scores_checked;
        """
    )
