"""Form answers: an Application's form questions and the answers prepared from Evidence."""

from alembic import op

revision = "0027"
down_revision = "0026"


def upgrade() -> None:
    op.execute(
        """
        -- One row per question, in the form's order. kind says how it's answered: contact from
        -- the Profile, write from Evidence, attach a file, yourself, or demographic (blank).
        CREATE TABLE form_answers (
            id bigserial PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            application_id uuid NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
            position integer NOT NULL,
            question text NOT NULL,
            kind text NOT NULL
                CHECK (kind IN ('contact', 'write', 'attach', 'yourself', 'demographic')),
            -- Which Profile value a contact field takes: name, first_name, last_name, email,
            -- phone or contact.
            field text,
            options jsonb NOT NULL DEFAULT '[]',
            required boolean NOT NULL DEFAULT false,
            origin text NOT NULL CHECK (origin IN ('greenhouse', 'common', 'pasted')),
            -- The verified sentences, as Claims; NULL until written.
            answer jsonb,
            -- Sentences Verification took out, with why.
            removed jsonb NOT NULL DEFAULT '[]'
        );
        CREATE INDEX form_answers_application ON form_answers (application_id, position);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE form_answers;")
