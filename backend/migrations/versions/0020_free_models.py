"""Running on free models: Groq's Zero Data Retention confirmation, and when paid models are out."""

from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade() -> None:
    op.execute(
        """
        -- Groq may receive personal data only after the person confirms they turned on
        -- Zero Data Retention in Groq's console, which the app can't check itself.
        ALTER TABLE users ADD COLUMN groq_zdr_confirmed boolean NOT NULL DEFAULT false;
        -- A credit or key error stops paid calls until then, with the reason shown on Settings.
        ALTER TABLE users ADD COLUMN paid_unavailable_until timestamptz;
        ALTER TABLE users ADD COLUMN paid_unavailable_reason text;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE users DROP COLUMN groq_zdr_confirmed;
        ALTER TABLE users DROP COLUMN paid_unavailable_until;
        ALTER TABLE users DROP COLUMN paid_unavailable_reason;
        """
    )
