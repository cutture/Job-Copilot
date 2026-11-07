"""Where to look first to fix a failed Eval Case."""

from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade() -> None:
    op.execute("ALTER TABLE eval_results ADD COLUMN fix_area text;")
