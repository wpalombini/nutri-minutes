"""Write normalised articles, licences and relations, following docs/database.md."""

import json
from enum import StrEnum
from typing import Any

from sqlalchemy import Connection, text

from pipeline.scout.normalise import SOURCE, ArticleValues, RecordError

# Source codes Europe PMC uses for the identifiers we store.
_TARGET_COLUMNS = {"MED": "pmid", "PMC": "pmcid"}


class IdentifierConflict(RecordError):
    """The record's identifiers point at different stored articles, or disagree with one."""


class Outcome(StrEnum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


def _find_matches(conn: Connection, values: ArticleValues) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, doi, pmid, pmcid FROM articles "
            "WHERE doi = :doi OR pmid = :pmid OR pmcid = :pmcid "
            "ORDER BY id FOR UPDATE"
        ),
        {"doi": values.doi, "pmid": values.pmid, "pmcid": values.pmcid},
    ).mappings()
    return [dict(row) for row in rows]


def _article_params(values: ArticleValues) -> dict[str, Any]:
    return {
        "doi": values.doi,
        "pmid": values.pmid,
        "pmcid": values.pmcid,
        "title": values.title,
        "abstract": values.abstract,
        "authors": values.authors,
        "journal": values.journal,
        "publication_types": values.publication_types,
        "language": values.language,
        "published_on": values.published_on,
        "first_indexed_on": values.first_indexed_on,
        "source": SOURCE,
        "source_record": json.dumps(values.source_record),
    }


def _upsert_article(conn: Connection, values: ArticleValues) -> tuple[int, Outcome]:
    matches = _find_matches(conn, values)
    if len(matches) > 1:
        raise IdentifierConflict("Identifiers match more than one stored article")
    params = _article_params(values)
    if not matches:
        article_id = conn.execute(
            text(
                "INSERT INTO articles (doi, pmid, pmcid, title, abstract, authors, journal, "
                "publication_types, language, published_on, first_indexed_on, source, "
                "source_record) VALUES (:doi, :pmid, :pmcid, :title, :abstract, :authors, "
                ":journal, :publication_types, :language, :published_on, :first_indexed_on, "
                ":source, CAST(:source_record AS jsonb)) RETURNING id"
            ),
            params,
        ).scalar_one()
        return int(article_id), Outcome.INSERTED

    stored = matches[0]
    for column in ("doi", "pmid", "pmcid"):
        incoming = params[column]
        if incoming is not None and stored[column] is not None and stored[column] != incoming:
            raise IdentifierConflict(f"Stored {column} differs from the incoming one")
    # Fields other than identifiers are derived from the record, so comparing the record and
    # the identifiers is enough to tell whether anything changed.
    changed = conn.execute(
        text(
            "UPDATE articles SET doi = coalesce(:doi, doi), pmid = coalesce(:pmid, pmid), "
            "pmcid = coalesce(:pmcid, pmcid), title = :title, abstract = :abstract, "
            "authors = :authors, journal = :journal, publication_types = :publication_types, "
            "language = :language, published_on = :published_on, "
            "first_indexed_on = :first_indexed_on, source = :source, "
            "source_record = CAST(:source_record AS jsonb), updated_at = now() "
            "WHERE id = :id AND (source_record IS DISTINCT FROM CAST(:source_record AS jsonb) "
            "OR doi IS DISTINCT FROM coalesce(:doi, doi) "
            "OR pmid IS DISTINCT FROM coalesce(:pmid, pmid) "
            "OR pmcid IS DISTINCT FROM coalesce(:pmcid, pmcid)) RETURNING id"
        ),
        {**params, "id": stored["id"]},
    ).first()
    return int(stored["id"]), Outcome.UPDATED if changed else Outcome.UNCHANGED


def _record_licence(conn: Connection, article_id: int, values: ArticleValues) -> None:
    licence = values.licence
    touched = conn.execute(
        text(
            "UPDATE article_licences SET last_seen_at = now() WHERE id = ("
            "  SELECT id FROM article_licences WHERE article_id = :article_id AND source = :source"
            "  ORDER BY last_seen_at DESC, id DESC LIMIT 1"
            ") AND licence_code = :code AND raw_value IS NOT DISTINCT FROM :raw RETURNING id"
        ),
        {
            "article_id": article_id,
            "source": SOURCE,
            "code": licence.licence_code,
            "raw": licence.raw_value,
        },
    ).first()
    if touched is None:
        conn.execute(
            text(
                "INSERT INTO article_licences (article_id, source, raw_value, licence_code) "
                "VALUES (:article_id, :source, :raw, :code)"
            ),
            {
                "article_id": article_id,
                "source": SOURCE,
                "raw": licence.raw_value,
                "code": licence.licence_code,
            },
        )


def _record_relations(conn: Connection, article_id: int, values: ArticleValues) -> None:
    for relation in values.relations:
        column = _TARGET_COLUMNS.get(relation.target_source)
        related_id = None
        if column is not None:
            related_id = conn.execute(
                text(f"SELECT id FROM articles WHERE {column} = :target_id"),  # noqa: S608
                {"target_id": relation.target_id},
            ).scalar()
        conn.execute(
            text(
                "INSERT INTO article_relations (article_id, relation_type, raw_type, "
                "target_source, target_id, related_article_id) VALUES (:article_id, "
                ":relation_type, :raw_type, :target_source, :target_id, :related_id) "
                "ON CONFLICT (article_id, raw_type, target_source, target_id) DO UPDATE SET "
                "last_seen_at = now(), relation_type = excluded.relation_type, "
                "related_article_id = coalesce(excluded.related_article_id, "
                "article_relations.related_article_id)"
            ),
            {
                "article_id": article_id,
                "relation_type": relation.relation_type,
                "raw_type": relation.raw_type,
                "target_source": relation.target_source,
                "target_id": relation.target_id,
                "related_id": related_id,
            },
        )
    # Link relations stored before this article arrived.
    conn.execute(
        text(
            "UPDATE article_relations SET related_article_id = :article_id "
            "WHERE related_article_id IS NULL AND ("
            "(target_source = 'MED' AND target_id = :pmid) OR "
            "(target_source = 'PMC' AND target_id = :pmcid))"
        ),
        {"article_id": article_id, "pmid": values.pmid, "pmcid": values.pmcid},
    )


def store(conn: Connection, values: ArticleValues) -> Outcome:
    """Store one article with its licence and relations. The caller owns the transaction."""
    article_id, outcome = _upsert_article(conn, values)
    _record_licence(conn, article_id, values)
    _record_relations(conn, article_id, values)
    return outcome
