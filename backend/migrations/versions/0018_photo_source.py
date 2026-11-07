"""Whether the photo came from the uploaded resume or was added by the person."""

from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade() -> None:
    op.execute(
        """
        -- show_photo now means the person asked to add a photo of their own, since their resume
        -- has none. A resume's own photo is used without asking.
        ALTER TABLE profiles ADD COLUMN photo_from_resume boolean NOT NULL DEFAULT false;
        """
    )
