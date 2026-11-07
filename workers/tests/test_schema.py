"""Constraints and permissions in the Scout tables."""

from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError, ProgrammingError


def _insert_article(conn: Connection, **overrides: Any) -> int:
    values: dict[str, Any] = {
        "doi": "10.1000/example",
        "pmid": "12345",
        "pmcid": None,
        "title": "A study",
        "source": "europe_pmc",
        "source_record": "{}",
    }
    values.update(overrides)
    article_id = conn.execute(
        text(
            "INSERT INTO articles (doi, pmid, pmcid, title, source, source_record) "
            "VALUES (:doi, :pmid, :pmcid, :title, :source, CAST(:source_record AS jsonb)) "
            "RETURNING id"
        ),
        values,
    ).scalar_one()
    return int(article_id)


def _expect_violation(conn: Connection, statement: str, params: dict[str, Any]) -> None:
    savepoint = conn.begin_nested()
    with pytest.raises(IntegrityError):
        conn.execute(text(statement), params)
    savepoint.rollback()


def test_article_defaults(conn: Connection) -> None:
    article_id = _insert_article(conn)
    row = conn.execute(
        text("SELECT publication_types, first_seen_at FROM articles WHERE id = :id"),
        {"id": article_id},
    ).one()
    assert row.publication_types == []
    assert row.first_seen_at is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"doi": None, "pmid": None, "pmcid": None},
        {"doi": "10.1000/UPPER"},
        {"doi": "https://doi.org/10.1000/x"},
        {"doi": "10.1000/has space"},
        {"pmid": "PMID123"},
        {"pmid": "0123"},
        {"pmcid": "12345"},
        {"pmcid": "pmc12345"},
    ],
)
def test_article_identifier_checks(conn: Connection, overrides: dict[str, Any]) -> None:
    savepoint = conn.begin_nested()
    with pytest.raises(IntegrityError):
        _insert_article(conn, **overrides)
    savepoint.rollback()


def test_article_identifiers_are_unique(conn: Connection) -> None:
    _insert_article(conn, doi="10.1000/a", pmid="1")
    for overrides in ({"doi": "10.1000/a", "pmid": "2"}, {"doi": "10.1000/b", "pmid": "1"}):
        savepoint = conn.begin_nested()
        with pytest.raises(IntegrityError):
            _insert_article(conn, **overrides)
        savepoint.rollback()


def test_missing_identifiers_dont_collide(conn: Connection) -> None:
    _insert_article(conn, doi="10.1000/a", pmid=None)
    _insert_article(conn, doi="10.1000/b", pmid=None)


@pytest.mark.parametrize(
    ("licence_code", "allowed"),
    [
        ("cc0", True),
        ("cc-by", True),
        ("cc-by-sa", False),
        ("cc-by-nc", False),
        ("other", False),
        ("unknown", False),
    ],
)
def test_full_text_reuse_is_generated(conn: Connection, licence_code: str, allowed: bool) -> None:
    article_id = _insert_article(conn)
    reuse = conn.execute(
        text(
            "INSERT INTO article_licences (article_id, source, licence_code) "
            "VALUES (:id, 'europe_pmc', :code) RETURNING full_text_reuse_allowed"
        ),
        {"id": article_id, "code": licence_code},
    ).scalar_one()
    assert reuse is allowed


def test_licence_code_check(conn: Connection) -> None:
    article_id = _insert_article(conn)
    _expect_violation(
        conn,
        "INSERT INTO article_licences (article_id, source, licence_code) "
        "VALUES (:id, 'europe_pmc', 'cc by')",
        {"id": article_id},
    )


def test_relation_type_check_and_uniqueness(conn: Connection) -> None:
    article_id = _insert_article(conn)
    insert = (
        "INSERT INTO article_relations "
        "(article_id, relation_type, raw_type, target_source, target_id) "
        "VALUES (:id, :type, 'Retraction in', 'MED', '42726688')"
    )
    conn.execute(text(insert), {"id": article_id, "type": "retraction_in"})
    _expect_violation(conn, insert, {"id": article_id, "type": "retraction_in"})
    _expect_violation(
        conn,
        insert.replace("'42726688'", "'1'"),
        {"id": article_id, "type": "Retraction in"},
    )


RUN_INSERT = (
    "INSERT INTO pipeline_runs (agent, status, parameters, finished_at) "
    "VALUES (:agent, :status, CAST('{}' AS jsonb), :finished_at)"
)


def test_one_running_run_per_agent(conn: Connection) -> None:
    conn.execute(text(RUN_INSERT), {"agent": "scout", "status": "running", "finished_at": None})
    conn.execute(text(RUN_INSERT), {"agent": "triage", "status": "running", "finished_at": None})
    _expect_violation(
        conn, RUN_INSERT, {"agent": "scout", "status": "running", "finished_at": None}
    )


@pytest.mark.parametrize(
    ("status", "finished"),
    [("running", True), ("succeeded", False), ("partial", False), ("failed", False)],
)
def test_finished_at_matches_status(conn: Connection, status: str, finished: bool) -> None:
    _expect_violation(
        conn,
        RUN_INSERT,
        {"agent": "scout", "status": status, "finished_at": "2026-11-07" if finished else None},
    )


def test_run_status_check(conn: Connection) -> None:
    _expect_violation(
        conn, RUN_INSERT, {"agent": "scout", "status": "done", "finished_at": "2026-11-07"}
    )


def test_run_defaults(conn: Connection) -> None:
    conn.execute(text(RUN_INSERT), {"agent": "scout", "status": "running", "finished_at": None})
    row = conn.execute(text("SELECT counts, resume_count FROM pipeline_runs")).one()
    assert row.counts == {}
    assert row.resume_count == 0


def test_worker_role_can_write_but_not_delete_or_change_schema(conn: Connection) -> None:
    conn.execute(text("SET LOCAL ROLE pipeline_worker"))
    article_id = _insert_article(conn)
    conn.execute(text("UPDATE articles SET title = 'Updated' WHERE id = :id"), {"id": article_id})
    run_id = conn.execute(
        text(
            "INSERT INTO pipeline_runs (agent, status, parameters) "
            "VALUES ('scout', 'running', CAST('{}' AS jsonb)) RETURNING id"
        )
    ).scalar_one()
    conn.execute(
        text("INSERT INTO pipeline_run_errors (run_id, source, error) VALUES (:id, 'x', 'bad')"),
        {"id": run_id},
    )
    for statement in (
        "DELETE FROM articles",
        "UPDATE pipeline_run_errors SET error = 'changed'",
        "CREATE TABLE not_allowed (id int)",
        "ALTER TABLE articles ADD COLUMN not_allowed int",
    ):
        savepoint = conn.begin_nested()
        with pytest.raises(ProgrammingError):
            conn.execute(text(statement))
        savepoint.rollback()
