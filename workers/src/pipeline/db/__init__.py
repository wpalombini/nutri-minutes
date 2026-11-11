"""Database access for the pipeline workers."""

import os

from sqlalchemy import Engine, create_engine

ENV_DATABASE_URL = "DATABASE_URL"


def database_url() -> str:
    """Return the SQLAlchemy URL from `DATABASE_URL`, using the psycopg 3 driver."""
    url = os.environ.get(ENV_DATABASE_URL)
    if not url:
        raise RuntimeError(f"{ENV_DATABASE_URL} is not set")
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError(f"{ENV_DATABASE_URL} must be a PostgreSQL URL")
    return url


def worker_engine() -> Engine:
    """An engine for a worker run, from `DATABASE_URL`.

    Parameters are hidden so record content never reaches error messages, logs or alerts, and
    TCP keepalives notice a dead connection, such as the lock connection, instead of hanging.
    """
    return create_engine(
        database_url(),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )
