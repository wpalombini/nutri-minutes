"""Constraints and permissions on `summaries` and `summary_limits`."""

from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from tests.test_extractor_schema import EXTRACTION, _extraction, _ids

COLUMNS = (
    "article_id",
    "run_id",
    "extraction_id",
    "model_call_id",
    "source_basis",
    "headline",
    "body",
    "result_sentence",
    "absolute_sentence",
)
# Built from the fixed column names above, never from input.
SUMMARY = (
    f"INSERT INTO summaries ({', '.join(COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join(':' + c for c in COLUMNS)}) RETURNING id"
)
LIMIT = (
    "INSERT INTO summary_limits (summary_id, position, statement) "
    "VALUES (:summary_id, :position, :statement)"
)


def _summary_ids(conn: Connection) -> dict[str, int]:
    ids = _ids(conn)
    ids["extraction_id"] = int(conn.execute(text(EXTRACTION), _extraction(ids)).scalar_one())
    return ids


def _summary(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "article_id": ids["article_id"],
        "run_id": ids["run_id"],
        "extraction_id": ids["extraction_id"],
        "model_call_id": ids["call_id"],
        "source_basis": "abstract",
        "headline": "More dairy linked to slightly fewer hip fractures",
        "body": "First paragraph.\n\nSecond paragraph.",
        "result_sentence": "Hip fracture risk was 9% lower among people who ate the most dairy.",
        "absolute_sentence": "That's 19 in every 1,000 people compared with 21 in every 1,000.",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    "overrides",
    [{}, {"absolute_sentence": None}, {"source_basis": "full_text"}, {"body": "One paragraph."}],
)
def test_valid_summaries(conn: Connection, overrides: dict[str, Any]) -> None:
    conn.execute(text(SUMMARY), _summary(_summary_ids(conn), **overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_basis": "metadata"},
        {"headline": ""},
        {"body": ""},
        {"result_sentence": ""},
        {"result_sentence": None},
        {"absolute_sentence": ""},
        {"headline": "Two\nlines"},
        {"headline": "Two\rlines"},
        {"result_sentence": "Two\nlines"},
        {"absolute_sentence": "Two\nlines"},
        {"extraction_id": -1},
    ],
)
def test_summary_checks(conn: Connection, overrides: dict[str, Any]) -> None:
    ids = _summary_ids(conn)
    with pytest.raises(IntegrityError):
        conn.execute(text(SUMMARY), _summary(ids, **overrides))


def _limit(summary_id: int, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "summary_id": summary_id,
        "position": 1,
        "statement": "Most people in it were women in Sweden, so it may not apply to everyone.",
    }
    values.update(overrides)
    return values


def test_valid_limits(conn: Connection) -> None:
    summary_id = conn.execute(text(SUMMARY), _summary(_summary_ids(conn))).scalar_one()
    for position in (1, 2, 3):
        conn.execute(text(LIMIT), _limit(summary_id, position=position))


@pytest.mark.parametrize(
    "overrides",
    [{"position": 0}, {"statement": ""}, {"statement": "Two\nlines"}, {"summary_id": -1}],
)
def test_limit_checks(conn: Connection, overrides: dict[str, Any]) -> None:
    summary_id = conn.execute(text(SUMMARY), _summary(_summary_ids(conn))).scalar_one()
    with pytest.raises(IntegrityError):
        conn.execute(text(LIMIT), {**_limit(summary_id), **overrides})


def test_limit_positions_are_unique(conn: Connection) -> None:
    summary_id = conn.execute(text(SUMMARY), _summary(_summary_ids(conn))).scalar_one()
    conn.execute(text(LIMIT), _limit(summary_id))
    with pytest.raises(IntegrityError):
        conn.execute(text(LIMIT), _limit(summary_id, statement="Another limit."))


def test_worker_role_can_only_add(conn: Connection) -> None:
    ids = _summary_ids(conn)
    conn.execute(text("SET LOCAL ROLE pipeline_worker"))
    summary_id = conn.execute(text(SUMMARY), _summary(ids)).scalar_one()
    conn.execute(text(LIMIT), _limit(summary_id))
    for statement in (
        "UPDATE summaries SET headline = 'x'",
        "DELETE FROM summaries",
        "UPDATE summary_limits SET statement = 'x'",
        "DELETE FROM summary_limits",
    ):
        savepoint = conn.begin_nested()
        with pytest.raises(ProgrammingError):
            conn.execute(text(statement))
        savepoint.rollback()
