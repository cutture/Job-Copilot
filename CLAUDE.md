# Job Copilot

- **Glossary:** use the terms in `CONTEXT.md`. When a term settles, update it in the same session and commit it on a `docs/` branch.
- **Wayfinding and issues:** read `docs/agents/issue-tracker.md` before touching tickets or the map.
- **Setup on a new clone:** run `git config core.hooksPath .githooks` so the personal-data checks run on commit and push. List private terms, such as your target city, in the gitignored `.private-terms`.
- **Triage labels and domain docs:** `docs/agents/triage-labels.md` and `docs/agents/domain.md`.
- **Prototypes:** run `python scripts/smoke_prototypes.py <screenshot-dir>` after changing one, and look at the screenshots. Every variant shows each decided requirement for its screen.
- **Live checks against the real models:** run `python scripts/live_check.py` with the app up. It uses an invented posting, prints counts only and deletes its own rows; extend it rather than writing a one-off.
- **Branches with a migration:** migrations only go forward, and the default Compose project holds the owner's real data. Run the branch as its own project, with `COMPOSE_PROJECT_NAME=jc-branch WEB_PORT=8766` set for both `docker compose up -d --build` and the live check, then `docker compose down -v` with the same name when done. The default project only ever runs `main`.
- **Personal data:** real resumes live outside this repo, in the parent folder. Fixtures and prototypes use invented data with `example.com` addresses.
