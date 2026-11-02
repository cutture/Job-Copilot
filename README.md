# Job-Copilot

A self-hosted job-search assistant. A person reviews everything and submits every application themselves.

## Run it

```sh
docker compose up --build
```

Then open http://127.0.0.1:8765, or set `WEB_PORT` to use another port. Local mode has no login and is reachable only from your own machine.

## Develop

Backend tests need a Postgres on port 55432, or set `TEST_DATABASE_URL`. They wipe that database.

```sh
docker run -d --name jc-test-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=job_copilot_test -p 127.0.0.1:55432:5432 postgres:17
cd backend && uv sync && uv run ruff check . && uv run mypy && uv run pytest
cd web && npm ci && npm run lint && npm run typecheck && npm test
```
