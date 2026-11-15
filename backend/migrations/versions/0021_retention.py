"""Retention: when Applications were opened and which Pack was sent, and trace deletions."""

from alembic import op

revision = "0021"
down_revision = "0020"


def upgrade() -> None:
    op.execute(
        """
        -- A Pack never submitted is deleted 90 days after its Application was last opened.
        ALTER TABLE applications ADD COLUMN opened_at timestamptz NOT NULL DEFAULT now();
        UPDATE applications SET opened_at = created_at;
        -- The Pack version sent, which stays with its Application; other versions go later.
        ALTER TABLE applications ADD COLUMN submitted_pack_id bigint;
        UPDATE applications a SET submitted_pack_id = (
            SELECT id FROM application_packs
            WHERE application_id = a.id AND user_id = a.user_id ORDER BY version DESC LIMIT 1)
        WHERE submitted_at IS NOT NULL;
        -- Every try counts towards Langfuse's 50 deletions a day; sent ones are kept a day or two.
        ALTER TABLE trace_deletions ADD COLUMN tried_at timestamptz;
        ALTER TABLE trace_deletions ADD COLUMN sent_at timestamptz;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE applications DROP COLUMN opened_at;
        ALTER TABLE applications DROP COLUMN submitted_pack_id;
        ALTER TABLE trace_deletions DROP COLUMN tried_at;
        ALTER TABLE trace_deletions DROP COLUMN sent_at;
        """
    )
