"""Applications and their Application Pack versions."""

from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE applications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users (id),
            job_posting_id uuid NOT NULL REFERENCES job_postings (id),
            source text NOT NULL,
            -- The rating the person saw when they clicked Apply.
            band text NOT NULL,
            requirements jsonb NOT NULL,
            rubric_version integer NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, job_posting_id)
        );

        CREATE TABLE application_packs (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users (id),
            application_id uuid NOT NULL REFERENCES applications (id),
            version integer NOT NULL,
            status text NOT NULL DEFAULT 'generating'
                CHECK (status IN ('generating', 'waiting', 'ready')),
            -- Why a waiting Pack is waiting, when that is known.
            failure text CHECK (failure IN ('model_unavailable', 'unusable_answer')),
            -- Documents are saved only once Verification has run on them.
            resume jsonb,
            cover_letter jsonb,
            removed_claims jsonb,
            model text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (application_id, version),
            CHECK (status <> 'ready' OR (resume IS NOT NULL AND cover_letter IS NOT NULL
                                         AND removed_claims IS NOT NULL))
        );
        """
    )
