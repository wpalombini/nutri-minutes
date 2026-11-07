"""Fixtures for tests that need a real Postgres database.

Set TEST_DATABASE_URL to a disposable database. Its schema is dropped and recreated. In CI,
REQUIRE_TEST_DATABASE=1 turns a missing database into a failure instead of a skip.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text

WORKERS_DIR = Path(__file__).resolve().parent.parent


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if os.environ.get("REQUIRE_TEST_DATABASE") == "1":
            pytest.fail("TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL is not set")
    return url


@pytest.fixture(scope="session")
def alembic_config(monkeypatch_session: pytest.MonkeyPatch) -> Config:
    monkeypatch_session.setenv("DATABASE_URL", _test_database_url())
    return Config(str(WORKERS_DIR / "alembic.ini"))


@pytest.fixture(scope="session")
def monkeypatch_session() -> Iterator[pytest.MonkeyPatch]:
    with pytest.MonkeyPatch.context() as mp:
        yield mp


@pytest.fixture(scope="session")
def engine(alembic_config: Config) -> Iterator[Engine]:
    from pipeline.db import database_url

    engine = create_engine(database_url())
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    """A connection whose changes are rolled back after each test."""
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()
