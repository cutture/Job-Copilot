"""Custom sections: headings the person names for what fits no standard section."""

from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade() -> None:
    op.execute(
        """
        -- Headings only, in order, from the uploaded file or written by the person.
        ALTER TABLE profiles ADD COLUMN custom_sections jsonb NOT NULL DEFAULT '[]';
        """
    )
