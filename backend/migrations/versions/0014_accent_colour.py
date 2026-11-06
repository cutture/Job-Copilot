"""The accent colour of a person's styled resume and cover letter."""

from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE profiles ADD COLUMN accent_colour text NOT NULL DEFAULT 'navy'
            CHECK (accent_colour IN ('navy', 'teal', 'burgundy', 'gold'));
        """
    )
