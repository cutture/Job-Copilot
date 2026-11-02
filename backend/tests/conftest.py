import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:test@127.0.0.1:55432/job_copilot_test"
)
os.environ["DATABASE_URL"] = TEST_DB

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def clean() -> None:
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("TRUNCATE jobs, job_postings")


@pytest.fixture
def client() -> Iterator[TestClient]:
    from job_copilot.api import app

    with TestClient(app) as test_client:
        yield test_client
