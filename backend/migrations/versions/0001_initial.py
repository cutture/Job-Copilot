"""Users, Job Postings and the Postgres-backed queue."""

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (id uuid PRIMARY KEY);
        INSERT INTO users (id) VALUES ('00000000-0000-0000-0000-000000000001');

        CREATE TABLE job_postings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users (id),
            source text NOT NULL,
            title text NOT NULL,
            text text NOT NULL,
            status text NOT NULL DEFAULT 'queued',
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX job_postings_user_created ON job_postings (user_id, created_at DESC);

        CREATE TABLE jobs (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            kind text NOT NULL,
            payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
