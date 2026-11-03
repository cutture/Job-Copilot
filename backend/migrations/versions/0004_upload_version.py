"""Number each uploaded resume, so a reading of an older one can be discarded."""

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.execute("ALTER TABLE profiles ADD COLUMN resume_version integer NOT NULL DEFAULT 0")
