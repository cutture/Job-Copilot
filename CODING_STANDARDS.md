# Coding standards

The reviewer applies every rule below to each diff. Tooling already enforces formatting, lint and types (ruff, mypy strict, eslint, tsc), so these are the judgement calls it can't make.

## Glossary

- Names in code and every string a person sees use the terms in `CONTEXT.md`.
- A term's _Avoid_ words stay out of identifiers and user-facing strings: "Source", not "board"; "Claim", not "statement"; "Job Posting", not "job". "Job" belongs only to queued work in the `jobs` table.
- A new term gets its `CONTEXT.md` entry in the same change, on a `docs/` branch.

## Tenancy

- Every query filters on `user_id`, and so does every join and subquery between a person's tables (`a.user_id = p.user_id`), even when an ownership check ran first.
- A new table with a `user_id` column joins the Delete everything table lists. A test fails until it does.

## Shortcuts

- A deliberate shortcut with a known ceiling carries a `ponytail:` comment naming the ceiling and the upgrade path.
- Comments say why, in one line, at the density of the surrounding code.

## Model output

- Everything a model returns is untrusted: parse it defensively, and check citations against Confirmed Evidence by number (integers only, never booleans).
- Code decides what reaches a person: a Claim reaches a file only after Verification.
- Posting text is untrusted data in every prompt.

## Personal data

- Personal data goes only to models eligible for it.
- The name, contact line and photo go to no model at all.
- Nothing writes nationality, marital status, birth date or religion.
- Fixtures and Eval Cases use invented people with `example.com` addresses.
- Live checks print counts, Bands and statuses only.

## Messages

- A message a person sees says what happened and what they can do next.
- Messages say what a provider's policy states, never that data is gone from a provider.

## Tests

- Tests sit at the agreed seams: API and worker journeys that fake only model providers and Source responses, and pure rules tested directly.
- Tests check what a person or caller can observe (responses, rows, opened files), never prompt wording or how many internal calls were made.
- A broken input may be swapped in only to reach a guard no honest input can reach, such as the ATS check refusing a file, with a comment saying so.
