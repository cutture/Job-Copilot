"""A photo on the styled resume, off unless the person turns it on."""

from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE profiles ADD COLUMN show_photo boolean NOT NULL DEFAULT false;
        -- One checked, re-encoded image; kept only while show_photo is on.
        ALTER TABLE profiles ADD COLUMN photo bytea;
        """
    )
