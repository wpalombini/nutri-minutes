"""Alembic environment: runs migrations online, one deploy at a time."""

from typing import Literal

from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.schema import SchemaItem

from pipeline.db import database_url
from pipeline.db.models import Base

# Arbitrary fixed key for the migration advisory lock, so two deploys can't migrate at once.
MIGRATION_LOCK_KEY = 7_042_156_001

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


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        connection.commit()
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
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
            connection.commit()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline mode is not supported. Run migrations against a database.")

run_migrations_online()
