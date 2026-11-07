"""The migrations apply, reverse and match the models."""

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

EXPECTED_TABLES = {
    "articles",
    "article_licences",
    "article_relations",
    "pipeline_runs",
    "pipeline_run_errors",
}


def test_models_match_migrations(engine: Engine, alembic_config: Config) -> None:
    command.check(alembic_config)


def test_downgrade_and_upgrade_again(engine: Engine, alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    assert EXPECTED_TABLES.isdisjoint(inspect(engine).get_table_names())

    command.upgrade(alembic_config, "head")
    assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
