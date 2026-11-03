"""The Watchlist, searches, and where each Job Posting came from."""

from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE watchlist (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users (id),
            source text NOT NULL,
            api_host text NOT NULL,
            token text NOT NULL,
            name text NOT NULL,
            failure text,
            last_checked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, source, token)
        );

        CREATE TABLE searches (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            created_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz
        );
        CREATE INDEX searches_user_created ON searches (user_id, created_at);

        ALTER TABLE job_postings
            ADD COLUMN watchlist_id uuid REFERENCES watchlist (id) ON DELETE SET NULL,
            ADD COLUMN external_id text,
            ADD COLUMN employer text,
            ADD COLUMN posted_on date,
            ADD COLUMN date_provided boolean NOT NULL DEFAULT true,
            ADD COLUMN credit_url text,
            ADD COLUMN apply_url text,
            ADD COLUMN expired_at timestamptz;
        CREATE UNIQUE INDEX job_postings_seen ON job_postings (user_id, source, external_id)
            WHERE external_id IS NOT NULL;

        ALTER TABLE profiles
            ADD COLUMN search_window_days integer NOT NULL DEFAULT 15
                CHECK (search_window_days BETWEEN 1 AND 15),
            ADD COLUMN recheck_due boolean NOT NULL DEFAULT false;
        """
    )
