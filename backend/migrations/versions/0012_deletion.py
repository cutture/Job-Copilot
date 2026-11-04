"""What deletion leaves behind: changed Matches, postings not to fetch again, traces to delete."""

from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.execute(
        """
        -- Evidence a Match relied on was deleted; shown until the Match is rated again.
        ALTER TABLE matches ADD COLUMN profile_changed boolean NOT NULL DEFAULT false;

        -- A Source posting the person deleted, so a search doesn't add it back.
        CREATE TABLE deleted_postings (
            user_id uuid NOT NULL REFERENCES users (id),
            source text NOT NULL,
            external_id text NOT NULL,
            PRIMARY KEY (user_id, source, external_id)
        );

        -- Trace IDs to delete at the tracing service. Only the ID is kept, with no user.
        CREATE TABLE trace_deletions (
            trace_id text PRIMARY KEY,
            queued_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
