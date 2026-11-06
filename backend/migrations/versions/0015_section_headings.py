"""The section headings of a person's uploaded file, in its order."""

from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    op.execute(
        """
        -- Each {kind, heading, grouped}; empty means the default order. Only headings are kept.
        ALTER TABLE profiles ADD COLUMN resume_sections jsonb NOT NULL DEFAULT '[]';
        """
    )
