"""Eval Runs, their Eval Case results, and the invented person the cases run as."""

from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.execute(
        """
        -- Eval Cases run as this invented person, whose $3 cap stops evals first.
        INSERT INTO users (id, monthly_cap_usd)
        VALUES ('00000000-0000-0000-0000-00000000e7a1', 3) ON CONFLICT DO NOTHING;

        CREATE TABLE eval_runs (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            deepeval_version text NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            cost_usd numeric(12, 6)
        );

        CREATE TABLE eval_results (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            run_id bigint NOT NULL REFERENCES eval_runs (id) ON DELETE CASCADE,
            case_id text NOT NULL,
            area text NOT NULL,
            status text NOT NULL CHECK (status IN ('passed', 'failed', 'did_not_run')),
            hard_failure boolean NOT NULL DEFAULT false,
            -- A result counts only once the owner has checked the case's labels.
            labels_checked boolean NOT NULL,
            reason text NOT NULL
        );
        """
    )
