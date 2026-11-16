"""Change Requests: what each Pack version was asked to change."""

from alembic import op

revision = "0026"
down_revision = "0025"


def upgrade() -> None:
    op.execute(
        """
        -- Every Change Request so far, oldest first; a version is written with all of them.
        ALTER TABLE application_packs ADD COLUMN change_requests jsonb NOT NULL DEFAULT '[]';

        -- How many Pack versions were ever written, so a new one never reuses the number of
        -- one deleted with Back to previous version, and the cost estimate counts them all.
        ALTER TABLE applications ADD COLUMN versions_written integer NOT NULL DEFAULT 1;
        UPDATE applications a SET versions_written = v.most
        FROM (SELECT application_id, max(version) AS most FROM application_packs
              GROUP BY application_id) v
        WHERE v.application_id = a.id;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE applications DROP COLUMN versions_written; "
        "ALTER TABLE application_packs DROP COLUMN change_requests;"
    )
