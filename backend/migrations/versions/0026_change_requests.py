"""Change Requests: what each Pack version was asked to change."""

from alembic import op

revision = "0026"
down_revision = "0025"


def upgrade() -> None:
    op.execute(
        """
        -- Every Change Request so far, oldest first; a version is written with all of them.
        ALTER TABLE application_packs ADD COLUMN change_requests jsonb NOT NULL DEFAULT '[]';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE application_packs DROP COLUMN change_requests;")
