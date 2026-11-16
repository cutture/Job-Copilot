"""Pausing a model step that keeps failing."""

from alembic import op

revision = "0024"
down_revision = "0023"


def upgrade() -> None:
    op.execute(
        """
        -- Full Fallback List failures in a row for one model step; at three it pauses a while.
        CREATE TABLE step_pauses (
            user_id uuid NOT NULL REFERENCES users (id),
            step text NOT NULL,
            failures integer NOT NULL DEFAULT 0,
            paused_until timestamptz,
            PRIMARY KEY (user_id, step)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE step_pauses;")
