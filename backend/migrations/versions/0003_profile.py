"""Profile facts and preferences, and Evidence items."""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE profiles (
            user_id uuid PRIMARY KEY REFERENCES users (id),
            resume_filename text,
            resume_text text,
            extraction_status text,
            work_authorization text,
            lives_in text,
            languages text[] NOT NULL DEFAULT '{English}',
            seniority text,
            roles text[] NOT NULL DEFAULT '{}',
            work_type text NOT NULL DEFAULT 'employment_and_freelance',
            min_salary integer,
            location_arrangements text[] NOT NULL DEFAULT '{remote}',
            location_places text[] NOT NULL DEFAULT '{}',
            updated_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE evidence (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            origin text NOT NULL CHECK (origin IN ('resume', 'self_reported')),
            text text NOT NULL,
            confirmed boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX evidence_user ON evidence (user_id, id);
        """
    )
