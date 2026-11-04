"""Review, Submitted and Outcome; the Application each model call was for; a name for files."""

from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE application_packs ADD COLUMN reviewed_at timestamptz;

        ALTER TABLE applications
            ADD COLUMN submitted_at timestamptz,
            ADD COLUMN outcome text
                CHECK (outcome IN ('interview', 'offer', 'rejected', 'no_response')),
            ADD COLUMN outcome_at timestamptz,
            ADD CHECK (outcome IS NULL OR submitted_at IS NOT NULL);

        -- What an Application cost; the ledger keeps the row if the Application goes.
        ALTER TABLE model_calls
            ADD COLUMN application_id uuid REFERENCES applications (id) ON DELETE SET NULL;

        -- Shown only in downloaded documents, never sent to a model.
        ALTER TABLE profiles ADD COLUMN name text, ADD COLUMN contact text;
        """
    )
