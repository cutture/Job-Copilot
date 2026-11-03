"""Matches: the rating of a Job Posting that passed Filter."""

from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE matches (
            job_posting_id uuid PRIMARY KEY REFERENCES job_postings (id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users (id),
            band text NOT NULL CHECK (band IN ('High', 'Medium', 'Low')),
            nice_met integer NOT NULL,
            reasons jsonb NOT NULL,
            gaps jsonb NOT NULL,
            profile_prompts jsonb NOT NULL,
            requirements jsonb NOT NULL,
            rubric_version integer NOT NULL,
            rated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX matches_user ON matches (user_id);
        """
    )
