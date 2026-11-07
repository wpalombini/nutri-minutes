"""Alembic environment: runs migrations online, one deploy at a time."""

import logging
import time
from logging.config import fileConfig
from typing import Literal

from alembic import context
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.schema import SchemaItem

from pipeline.db import database_url
from pipeline.db.models import Base

# Arbitrary fixed key for the migration advisory lock, so two deploys can't migrate at once.
MIGRATION_LOCK_KEY = 7_042_156_001
# How long to wait for another deploy's migrations before giving up.
LOCK_WAIT_SECONDS = 300
LOCK_POLL_SECONDS = 2

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)

logger = logging.getLogger("alembic.env")
target_metadata = Base.metadata


def include_object(
    obj: SchemaItem,
    name: str | None,
    type_: Literal[
        "schema",
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
        "check_constraint",
    ],
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    """Ignore tables that exist in the database but have no model, such as web-owned tables."""
    return not (type_ == "table" and reflected and compare_to is None)


def _acquire_lock(connection: Connection) -> None:
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
        ).scalar_one()
        connection.commit()
        if acquired:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Another migration still holds the lock after {LOCK_WAIT_SECONDS} seconds"
            )
        time.sleep(LOCK_POLL_SECONDS)


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    try:
        with engine.connect() as connection:
            _acquire_lock(connection)
            try:
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    include_object=include_object,
                    compare_server_default=True,
                    transaction_per_migration=True,
                )
                with context.begin_transaction():
                    context.run_migrations()
                connection.commit()
            finally:
                # Clear any failed transaction first, or the unlock can't run. If the connection
                # dropped, the lock went with it, so don't hide the original error.
                try:
                    connection.rollback()
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY}
                    )
                    connection.commit()
                except DBAPIError:
                    logger.warning("Couldn't release the migration lock; it ends with the session")
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline mode is not supported. Run migrations against a database.")

run_migrations_online()
