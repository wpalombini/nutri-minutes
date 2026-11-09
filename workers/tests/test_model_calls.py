"""The `model_calls` table and the Postgres call log."""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from pipeline.models.calls import INSERT, PostgresCallLog, _params
from pipeline.models.client import CallAttempt, Outcome


def _run(conn: Connection) -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO pipeline_runs (agent, status, parameters) "
                "VALUES ('triage', 'running', CAST('{}' AS jsonb)) RETURNING id"
            )
        ).scalar_one()
    )


def _attempt(run_id: int, **overrides: Any) -> CallAttempt:
    values: dict[str, Any] = {
        "run_id": run_id,
        "stage": "triage",
        "article_id": None,
        "prompt_name": "triage/scope",
        "prompt_version": "abc123",
        "attempt": 1,
        "input_values": {"title": "Ünïcode"},
        "model_requested": "example/model-1.0",
        "max_cost_usd": Decimal("0.01"),
        "outcome": Outcome.SUCCEEDED,
        "raw_reply": "{}",
        "cost_usd": Decimal("0.0004"),
    }
    values.update(overrides)
    return CallAttempt(**values)


def test_log_records_and_sums_spend(clean_engine: Engine) -> None:
    with clean_engine.begin() as conn:
        run_id = _run(conn)
        other_run = _run_other(conn)
    log = PostgresCallLog(clean_engine)
    first = log.record(_attempt(run_id))
    log.record(_attempt(run_id, outcome=Outcome.ERROR, raw_reply=None, cost_usd=None, error="x"))
    log.record(_attempt(run_id, outcome=Outcome.REFUSED, raw_reply=None, cost_usd=None, error="b"))
    log.record(_attempt(run_id, stage="grader"))
    log.record(_attempt(other_run))
    assert first == 1
    assert log.spent_usd(run_id, "triage") == Decimal("0.0104")
    assert log.spent_usd(run_id, "writer") == 0
    with clean_engine.connect() as conn:
        row = conn.execute(text("SELECT input_values, outcome FROM model_calls WHERE id = 1")).one()
    assert row.input_values == {"title": "Ünïcode"}
    assert row.outcome == "succeeded"


def _run_other(conn: Connection) -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO pipeline_runs (agent, status, parameters, finished_at) "
                "VALUES ('triage', 'failed', CAST('{}' AS jsonb), now()) RETURNING id"
            )
        ).scalar_one()
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"outcome": "done"},
        {"attempt": 0},
        {"cost_usd": Decimal("-1")},
        {"raw_reply": None},
        {"error": "but it succeeded"},
    ],
)
def test_constraints(conn: Connection, overrides: dict[str, Any]) -> None:
    run_id = _run(conn)
    params = _params(_attempt(run_id, **overrides))
    savepoint = conn.begin_nested()
    with pytest.raises(IntegrityError):
        conn.execute(INSERT, params)
    savepoint.rollback()


def test_worker_role_can_insert_but_not_change_calls(conn: Connection) -> None:
    run_id = _run(conn)
    conn.execute(text("SET LOCAL ROLE pipeline_worker"))
    conn.execute(INSERT, _params(_attempt(run_id)))
    conn.execute(text("SELECT count(*) FROM model_calls")).scalar_one()
    for statement in ("UPDATE model_calls SET error = 'changed'", "DELETE FROM model_calls"):
        savepoint = conn.begin_nested()
        with pytest.raises(ProgrammingError):
            conn.execute(text(statement))
        savepoint.rollback()
