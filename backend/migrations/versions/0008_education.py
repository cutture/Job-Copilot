"""Education on the Profile, so degree Requirements can be judged."""

from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.execute("ALTER TABLE profiles ADD COLUMN education text")
