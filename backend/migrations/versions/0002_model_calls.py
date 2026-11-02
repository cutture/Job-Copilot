"""Monthly cap per user, and a record of every model call."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users ADD COLUMN monthly_cap_usd numeric(10, 2) NOT NULL DEFAULT 10;

        CREATE TABLE model_calls (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            model text NOT NULL,
            step text NOT NULL,
            input_tokens integer NOT NULL,
            output_tokens integer NOT NULL,
            cost_usd numeric(14, 8) NOT NULL,
            trace_id text,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX model_calls_user_created ON model_calls (user_id, created_at);
        """
    )
