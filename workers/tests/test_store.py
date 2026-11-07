"""Storing articles: matching, licence history and relations."""

from typing import Any

import pytest
from sqlalchemy import Connection, text

from pipeline.scout.normalise import normalise
from pipeline.scout.store import IdentifierConflict, Outcome, store
from tests.records import record


def _store(conn: Connection, **overrides: Any) -> Outcome:
    return store(conn, normalise(record(**overrides)))


def _licences(conn: Connection) -> list[tuple[str | None, str]]:
    rows = conn.execute(
        text("SELECT raw_value, licence_code FROM article_licences ORDER BY id")
    ).all()
    return [(row.raw_value, row.licence_code) for row in rows]


def test_insert_then_unchanged_then_updated(conn: Connection) -> None:
    assert _store(conn) is Outcome.INSERTED
    assert _store(conn) is Outcome.UNCHANGED
    assert _store(conn, title="A corrected title.") is Outcome.UPDATED
    row = conn.execute(text("SELECT title, authors FROM articles")).one()
    assert row.title == "A corrected title."
    assert row.authors == "Smith A, Jones B."


def test_match_fills_missing_identifiers(conn: Connection) -> None:
    _store(conn, pmcid=None, doi=None)
    assert _store(conn) is Outcome.UPDATED
    row = conn.execute(
        text("SELECT count(*) AS n, max(doi) AS doi, max(pmcid) AS pmcid FROM articles")
    ).one()
    assert (row.n, row.doi, row.pmcid) == (1, "10.1000/example.1", "PMC9000001")


def test_missing_incoming_identifier_keeps_stored_one(conn: Connection) -> None:
    _store(conn)
    _store(conn, pmcid=None)
    assert conn.execute(text("SELECT pmcid FROM articles")).scalar_one() == "PMC9000001"


def test_conflicting_identifier_changes_nothing(conn: Connection) -> None:
    _store(conn)
    with pytest.raises(IdentifierConflict):
        _store(conn, pmid="40000002", title="Changed")
    assert conn.execute(text("SELECT title FROM articles")).scalar_one().startswith("Protein")


def test_matches_on_two_articles_is_a_conflict(conn: Connection) -> None:
    _store(conn, id="1", pmid="1", doi="10.1000/a", pmcid=None)
    _store(conn, id="2", pmid="2", doi="10.1000/b", pmcid=None)
    with pytest.raises(IdentifierConflict):
        _store(conn, pmid="1", doi="10.1000/b", pmcid=None)


def test_licence_history(conn: Connection) -> None:
    _store(conn, license=None)
    _store(conn, license=None)
    _store(conn, license="cc by")
    _store(conn, license="cc by")
    _store(conn, license=None)
    assert _licences(conn) == [(None, "unknown"), ("cc by", "cc-by"), (None, "unknown")]
    current = conn.execute(
        text(
            "SELECT licence_code, full_text_reuse_allowed FROM article_licences "
            "ORDER BY last_seen_at DESC, id DESC LIMIT 1"
        )
    ).one()
    assert (current.licence_code, current.full_text_reuse_allowed) == ("unknown", False)


def test_relations_link_both_ways(conn: Connection) -> None:
    retraction = {"commentCorrection": [{"type": "Retraction in", "source": "MED", "id": "2"}]}
    _store(conn, id="1", pmid="1", doi="10.1000/a", pmcid=None, commentCorrectionList=retraction)
    unresolved = conn.execute(text("SELECT related_article_id FROM article_relations")).scalar()
    assert unresolved is None

    _store(conn, id="2", pmid="2", doi="10.1000/notice", pmcid=None)
    notice_id = conn.execute(text("SELECT id FROM articles WHERE pmid = '2'")).scalar_one()
    row = conn.execute(
        text("SELECT relation_type, related_article_id FROM article_relations")
    ).one()
    assert (row.relation_type, row.related_article_id) == ("retraction_in", notice_id)

    # Seeing the same link again doesn't add a row.
    _store(conn, id="1", pmid="1", doi="10.1000/a", pmcid=None, commentCorrectionList=retraction)
    assert conn.execute(text("SELECT count(*) FROM article_relations")).scalar_one() == 1


def test_relation_to_stored_article_is_linked_at_once(conn: Connection) -> None:
    _store(conn, id="2", pmid="2", doi="10.1000/notice", pmcid=None)
    _store(
        conn,
        id="1",
        pmid="1",
        doi="10.1000/a",
        pmcid=None,
        commentCorrectionList={
            "commentCorrection": {"type": "Erratum in", "source": "MED", "id": "2"}
        },
    )
    assert (
        conn.execute(text("SELECT related_article_id FROM article_relations")).scalar() is not None
    )
