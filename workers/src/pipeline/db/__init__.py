"""Database access for the pipeline workers."""

import os

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
