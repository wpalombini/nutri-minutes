"""Call logs: where the client records attempts and reads a run's spend."""

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, text

from pipeline.models.client import CallAttempt, Outcome

COLUMNS = (
    "run_id",
    "stage",
    "article_id",
    "prompt_name",
    "prompt_version",
    "attempt",
    "input_values",
    "model_requested",
    "model_answered",
    "provider",
    "generation_id",
    "outcome",
    "http_status",
    "raw_reply",
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "cost_usd",
    "max_cost_usd",
    "latency_ms",
    "error",
)
_VALUES = ", ".join(
    "CAST(:input_values AS jsonb)" if column == "input_values" else f":{column}"
    for column in COLUMNS
)
INSERT = text(
    f"INSERT INTO model_calls ({', '.join(COLUMNS)}) VALUES ({_VALUES}) RETURNING id"  # noqa: S608
)
SPENT = text(
    "SELECT COALESCE(SUM(COALESCE(cost_usd, max_cost_usd)), 0) FROM model_calls "
    "WHERE run_id = :run_id AND stage = :stage AND outcome <> 'refused'"
)


def _params(attempt: CallAttempt) -> dict[str, Any]:
    params = {column: getattr(attempt, column) for column in COLUMNS}
    params["input_values"] = json.dumps(dict(attempt.input_values), ensure_ascii=False)
    params["outcome"] = str(attempt.outcome)
    return params


class PostgresCallLog:
    """Each attempt is committed on its own connection, so traces survive the caller's rollback."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, attempt: CallAttempt) -> int:
        with self._engine.begin() as conn:
            return int(conn.execute(INSERT, _params(attempt)).scalar_one())

    def spent_usd(self, run_id: int, stage: str) -> Decimal:
        with self._engine.connect() as conn:
            value = conn.execute(SPENT, {"run_id": run_id, "stage": stage}).scalar_one()
        return Decimal(value)


class MemoryCallLog:
    """Keeps attempts in memory, for tests and one-off checks that have no pipeline run."""

    def __init__(self) -> None:
        self.attempts: list[CallAttempt] = []

    def record(self, attempt: CallAttempt) -> int:
        self.attempts.append(attempt)
        return len(self.attempts)

    def spent_usd(self, run_id: int, stage: str) -> Decimal:
        return sum(
            (
                a.cost_usd if a.cost_usd is not None else a.max_cost_usd
                for a in self.attempts
                if a.run_id == run_id and a.stage == stage and a.outcome is not Outcome.REFUSED
            ),
            Decimal(0),
        )
