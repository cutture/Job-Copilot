# Job-Copilot

A job-search assistant for one person, run on their own computer. A person reviews everything and submits every application themselves.

## Run it

Copy `.env.example` to `.env` and add your keys, then run the command below. A free Groq key is enough: without an Anthropic key, it uses free models that don't train on your data, once you turn on Zero Data Retention in Groq and tick the box on Settings.

```sh
docker compose up --build
```

Then open http://127.0.0.1:8765, or set `WEB_PORT` to use another port. It has no login, because it's reachable only from your own computer. It isn't built to be hosted anywhere else.

## Develop

Backend tests need a Postgres on port 55432, or set `TEST_DATABASE_URL`. They wipe that database.

```sh
docker run -d --name jc-test-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=job_copilot_test -p 127.0.0.1:55432:5432 postgres:17
cd backend && uv sync && uv run ruff check . && uv run mypy && uv run pytest
cd web && npm ci && npm run lint && npm run typecheck && npm test
```
