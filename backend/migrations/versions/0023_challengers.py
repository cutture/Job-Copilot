"""Challengers: each step's approved model, the models a case used, and Challenger runs."""

from alembic import op

revision = "0023"
down_revision = "0022"


def upgrade() -> None:
    op.execute(
        """
        -- A model the owner approved for one step, tried before that step's Fallback List.
        CREATE TABLE step_models (
            user_id uuid NOT NULL REFERENCES users (id),
            step text NOT NULL,
            model text NOT NULL,
            approved_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, step)
        );
        -- A recommendation the owner dismissed; it shows again only after a newer Challenger run.
        CREATE TABLE dismissed_recommendations (
            user_id uuid NOT NULL REFERENCES users (id),
            step text NOT NULL,
            model text NOT NULL,
            dismissed_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, step, model)
        );
        -- The model each step used for one case, so runs compare only on the same models.
        ALTER TABLE eval_results ADD COLUMN models jsonb;
        -- A Challenger run tries one model on one step; other runs leave these null.
        ALTER TABLE eval_runs ADD COLUMN challenger_step text;
        ALTER TABLE eval_runs ADD COLUMN challenger_model text;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE step_models;
        DROP TABLE dismissed_recommendations;
        ALTER TABLE eval_results DROP COLUMN models;
        ALTER TABLE eval_runs DROP COLUMN challenger_step;
        ALTER TABLE eval_runs DROP COLUMN challenger_model;
        """
    )
