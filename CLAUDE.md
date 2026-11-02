# Job Copilot

- **Glossary:** use the terms in `CONTEXT.md`. When a term settles, update it in the same session and commit it on a `docs/` branch.
- **Wayfinding and issues:** read `docs/agents/issue-tracker.md` before touching tickets or the map.
- **Setup on a new clone:** run `git config core.hooksPath .githooks` so the personal-data checks run on commit and push. List private terms, such as your target city, in the gitignored `.private-terms`.
- **Triage labels and domain docs:** `docs/agents/triage-labels.md` and `docs/agents/domain.md`.
- **Prototypes:** run `python scripts/smoke_prototypes.py <screenshot-dir>` after changing one, and look at the screenshots. Every variant shows each decided requirement for its screen.
- **Personal data:** real resumes live outside this repo, in the parent folder. Fixtures and prototypes use invented data with `example.com` addresses.
