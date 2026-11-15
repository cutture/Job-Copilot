"""Retention: when each Application was last opened, and when each trace deletion was sent."""

from alembic import op

revision = "0021"
down_revision = "0020"


def upgrade() -> None:
    op.execute(
        """
        -- A Pack never submitted is deleted 90 days after its Application was last opened.
        ALTER TABLE applications ADD COLUMN opened_at timestamptz NOT NULL DEFAULT now();
        UPDATE applications SET opened_at = created_at;
        -- Sent deletions are kept a day or two, to hold to Langfuse's 50 deletions a day.
        ALTER TABLE trace_deletions ADD COLUMN sent_at timestamptz;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE applications DROP COLUMN opened_at;
        ALTER TABLE trace_deletions DROP COLUMN sent_at;
        """
    )
