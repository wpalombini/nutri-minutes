"""Constraints and permissions on `article_stages` and `triage_decisions`."""

from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from tests.triage_helpers import insert_article

DECISION = (
    "INSERT INTO triage_decisions (article_id, run_id, decided_by, rule, model_call_id, "
    "in_scope, relevance, topics, primary_topic, reason) VALUES (:article_id, :run_id, "
    ":decided_by, :rule, :model_call_id, :in_scope, :relevance, :topics, :primary_topic, 'r')"
)


def _setup(conn: Connection) -> dict[str, int]:
    article_id = insert_article(conn, 1)
    run_id = conn.execute(
        text(
            "INSERT INTO pipeline_runs (agent, status, parameters) "
            "VALUES ('triage', 'running', CAST('{}' AS jsonb)) RETURNING id"
        )
    ).scalar_one()
    call_id = conn.execute(
        text(
            "INSERT INTO model_calls (run_id, stage, prompt_name, prompt_version, attempt, "
            "input_values, model_requested, outcome, raw_reply, max_cost_usd) VALUES "
            "(:run_id, 'triage', 'triage/scope', 'v', 1, CAST('{}' AS jsonb), 'm', "
            "'succeeded', '{}', 0) RETURNING id"
        ),
        {"run_id": run_id},
    ).scalar_one()
    return {"article_id": article_id, "run_id": int(run_id), "call_id": int(call_id)}


def _model(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "article_id": ids["article_id"],
        "run_id": ids["run_id"],
        "decided_by": "model",
        "rule": None,
        "model_call_id": ids["call_id"],
        "in_scope": True,
        "relevance": 3,
        "topics": ["bone-health", "longevity"],
        "primary_topic": "bone-health",
    }
    values.update(overrides)
    return values


def _rule(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    values = _model(
        ids,
        decided_by="rule",
        rule="no_abstract",
        model_call_id=None,
        in_scope=False,
        relevance=None,
        topics=[],
        primary_topic=None,
    )
    values.update(overrides)
    return values


def test_valid_decisions(conn: Connection) -> None:
    ids = _setup(conn)
    conn.execute(text(DECISION), _model(ids))
    conn.execute(text(DECISION), _model(ids, in_scope=False, topics=[], primary_topic=None))
    conn.execute(text(DECISION), _rule(ids))


@pytest.mark.parametrize(
    ("kind", "overrides"),
    [
        ("model", {"decided_by": "person"}),
        ("model", {"model_call_id": None}),
        ("model", {"relevance": None}),
        ("model", {"rule": "no_abstract"}),
        ("model", {"relevance": 6}),
        ("model", {"topics": ["bone-health", "sport"]}),
        ("model", {"primary_topic": "longevity", "topics": ["bone-health"]}),
        ("model", {"primary_topic": None}),
        ("model", {"in_scope": False}),
        ("rule", {"rule": None}),
        ("rule", {"in_scope": True, "topics": ["bone-health"], "primary_topic": "bone-health"}),
        ("rule", {"relevance": 2}),
    ],
)
def test_decision_checks(conn: Connection, kind: str, overrides: dict[str, Any]) -> None:
    ids = _setup(conn)
    params = _model(ids, **overrides) if kind == "model" else _rule(ids, **overrides)
    with pytest.raises(IntegrityError):
        conn.execute(text(DECISION), params)


@pytest.mark.parametrize(("status", "error"), [("failed", None), ("done", "x"), ("pending", None)])
def test_stage_checks(conn: Connection, status: str, error: str | None) -> None:
    ids = _setup(conn)
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO article_stages (article_id, agent, status, run_id, error) "
                "VALUES (:a, 'triage', :s, :r, :e)"
            ),
            {"a": ids["article_id"], "s": status, "r": ids["run_id"], "e": error},
        )


def test_worker_role_access(conn: Connection) -> None:
    ids = _setup(conn)
    conn.execute(text("SET LOCAL ROLE pipeline_worker"))
    conn.execute(text(DECISION), _model(ids))
    conn.execute(
        text(
            "INSERT INTO article_stages (article_id, agent, status, run_id, error) "
            "VALUES (:a, 'triage', 'failed', :r, 'x') ON CONFLICT (article_id, agent) "
            "DO UPDATE SET status = 'done', error = NULL"
        ),
        {"a": ids["article_id"], "r": ids["run_id"]},
    )
    conn.execute(text("UPDATE article_stages SET status = 'done', error = NULL"))
    for statement in (
        "UPDATE triage_decisions SET reason = 'changed'",
        "DELETE FROM triage_decisions",
        "DELETE FROM article_stages",
    ):
        savepoint = conn.begin_nested()
        with pytest.raises(ProgrammingError):
            conn.execute(text(statement))
        savepoint.rollback()
