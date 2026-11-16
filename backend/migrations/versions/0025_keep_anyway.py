"""Keep Anyway: the draft a Pack's documents are placed from, and each decision."""

from alembic import op

revision = "0025"
down_revision = "0024"


def upgrade() -> None:
    op.execute(
        """
        -- The writer's draft, before Verification: where each Claim goes when it's kept or
        -- comes back. NULL for Packs written before it was saved.
        ALTER TABLE application_packs ADD COLUMN draft jsonb;

        -- Every Keep Anyway decision, and every undoing of one. They go with their Application,
        -- and hold the Claim's draft ID, never its text, so nothing personal outlives the Pack.
        CREATE TABLE keep_decisions (
            id bigserial PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            application_id uuid NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
            claim_id text NOT NULL,
            kept boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE keep_decisions; ALTER TABLE application_packs DROP COLUMN draft;")
