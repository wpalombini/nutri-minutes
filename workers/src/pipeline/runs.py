"""Run tracking for pipeline agents, following the `pipeline_runs` rules in docs/database.md.

A worker holds a session-level advisory lock for its agent on a dedicated connection. A
`running` row found while holding the lock belongs to a dead worker.
"""

import json
import zlib
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError


class LockLost(RuntimeError):
    """The connection holding the agent's lock dropped, so another worker may take over."""


@dataclass
class Run:
    id: int
    agent: str
    parameters: dict[str, Any]
    checkpoint: dict[str, Any] | None
    counts: dict[str, int]
    resume_count: int


def lock_key(agent: str) -> int:
    """A stable advisory lock key per agent, distinct from the migration lock."""
    return zlib.crc32(f"pipeline-agent:{agent}".encode())


class AgentLock:
    """The agent's advisory lock, held on its own autocommit connection."""

    def __init__(self, connection: Connection, agent: str) -> None:
        self._connection = connection
        self.agent = agent

    def check(self) -> None:
        """Raise `LockLost` if the lock connection has dropped."""
        try:
            self._connection.execute(text("SELECT 1"))
        except DBAPIError as exc:
            raise LockLost(f"Lost the lock connection for {self.agent}") from exc


@contextmanager
def agent_lock(engine: Engine, agent: str) -> Iterator[AgentLock | None]:
    """Yield the lock if it was free, or None if another worker holds it."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        key = lock_key(agent)
        # Bound every statement on this connection, so a lock check can't hang forever.
        connection.execute(text("SET statement_timeout = '30s'"))
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
        ).scalar_one()
        try:
            yield AgentLock(connection, agent) if acquired else None
        finally:
            # If the connection dropped, the lock already went with it. Any error here must
            # not replace the one that ended the run, such as LockLost.
            with suppress(SQLAlchemyError):
                if acquired:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                connection.execute(text("RESET statement_timeout"))


def _run_from_row(row: Any) -> Run:
    return Run(
        id=int(row.id),
        agent=row.agent,
        parameters=dict(row.parameters),
        checkpoint=dict(row.checkpoint) if row.checkpoint is not None else None,
        counts={k: int(v) for k, v in row.counts.items()},
        resume_count=int(row.resume_count),
    )


def find_running(conn: Connection, agent: str) -> Run | None:
    row = conn.execute(
        text(
            "SELECT id, agent, parameters, checkpoint, counts, resume_count FROM pipeline_runs "
            "WHERE agent = :agent AND status = 'running' FOR UPDATE"
        ),
        {"agent": agent},
    ).first()
    return _run_from_row(row) if row is not None else None


def start_run(conn: Connection, agent: str, parameters: dict[str, Any]) -> Run:
    row = conn.execute(
        text(
            "INSERT INTO pipeline_runs (agent, status, parameters) "
            "VALUES (:agent, 'running', CAST(:parameters AS jsonb)) "
            "RETURNING id, agent, parameters, checkpoint, counts, resume_count"
        ),
        {"agent": agent, "parameters": json.dumps(parameters)},
    ).one()
    return _run_from_row(row)


def mark_resumed(conn: Connection, run: Run) -> None:
    run.resume_count += 1
    conn.execute(
        text("UPDATE pipeline_runs SET resume_count = :count WHERE id = :id"),
        {"count": run.resume_count, "id": run.id},
    )


def save_progress(
    conn: Connection, run: Run, checkpoint: dict[str, Any], counts: dict[str, int]
) -> None:
    """Save progress in the caller's transaction. Update `run` only after it commits."""
    conn.execute(
        text(
            "UPDATE pipeline_runs SET checkpoint = CAST(:checkpoint AS jsonb), "
            "counts = CAST(:counts AS jsonb) WHERE id = :id AND status = 'running'"
        ),
        {
            "checkpoint": json.dumps(checkpoint),
            "counts": json.dumps(counts),
            "id": run.id,
        },
    )


def finish_run(conn: Connection, run: Run, status: str, error: str | None = None) -> None:
    if status not in {"succeeded", "partial", "failed"}:
        raise ValueError(f"Not a final status: {status}")
    conn.execute(
        text(
            "UPDATE pipeline_runs SET status = :status, error = :error, "
            "counts = CAST(:counts AS jsonb), finished_at = now() "
            "WHERE id = :id AND status = 'running'"
        ),
        {"status": status, "error": error, "counts": json.dumps(run.counts), "id": run.id},
    )


def record_error(
    conn: Connection,
    run: Run,
    *,
    source: str,
    source_record_id: str | None,
    error: str,
    raw_record: Any,
) -> None:
    """Log a failed record without ever aborting the caller's transaction.

    If the full entry can't be stored, it retries without the raw record, then without the
    source ID. Each attempt runs in its own savepoint. Only the last failure is raised.
    """
    try:
        raw = json.dumps(raw_record, allow_nan=False)
    except TypeError, ValueError:
        raw = None
    statement = text(
        "INSERT INTO pipeline_run_errors (run_id, source, source_record_id, error, raw_record) "
        "VALUES (:run_id, :source, :source_record_id, :error, CAST(:raw AS jsonb))"
    )
    base: dict[str, Any] = {"run_id": run.id, "source": source, "error": error}
    attempts: list[dict[str, str | None]] = [
        {"source_record_id": source_record_id, "raw": raw},
        {"source_record_id": source_record_id, "raw": None},
        {"source_record_id": None, "raw": None},
    ]
    for number, attempt in enumerate(attempts, start=1):
        savepoint = conn.begin_nested()
        try:
            conn.execute(statement, {**base, **attempt})
        except Exception:
            savepoint.rollback()
            if number == len(attempts):
                raise
        else:
            savepoint.commit()
            return
