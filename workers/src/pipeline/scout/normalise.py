"""Turn Europe PMC records into article, licence and relation values.

Everything here is pure, so it can be tested without a database or network. Invalid input
raises `RecordError`, and the caller logs the record for review.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pipeline.db.models import LICENCE_CODES, RELATION_TYPES

SOURCE = "europe_pmc"


class RecordError(ValueError):
    """A record can't be stored as it is. The message must not contain secrets."""


@dataclass(frozen=True)
class Licence:
    raw_value: str | None
    licence_code: str


@dataclass(frozen=True)
class Relation:
    relation_type: str
    raw_type: str
    target_source: str
    target_id: str


@dataclass(frozen=True)
class ArticleValues:
    doi: str | None
    pmid: str | None
    pmcid: str | None
    title: str
    abstract: str | None
    authors: str | None
    journal: str | None
    publication_types: list[str]
    language: str | None
    published_on: date | None
    first_indexed_on: date | None
    source_record: dict[str, Any]
    licence: Licence
    relations: list[Relation] = field(default_factory=list)


_DOI_PREFIX = re.compile(r"^(?:doi:\s*|(?:https?://)?(?:dx\.)?doi\.org/)", re.IGNORECASE)
_DOI = re.compile(r"^10\.\S+$")
_PMID = re.compile(r"^[1-9][0-9]*$")
_PMCID = re.compile(r"^PMC[1-9][0-9]*$")
_LICENCE_VERSION = re.compile(r"[-\s]+\d+(?:\.\d+)*$")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecordError(f"Expected text, got {type(value).__name__}")
    stripped = value.strip()
    return stripped or None


def canonical_doi(value: Any) -> str | None:
    doi = _text(value)
    if doi is None:
        return None
    doi = _DOI_PREFIX.sub("", doi).strip().lower()
    if not _DOI.match(doi):
        raise RecordError("Invalid DOI")
    return doi


def canonical_pmid(value: Any) -> str | None:
    pmid = _text(value)
    if pmid is None:
        return None
    if not _PMID.match(pmid):
        raise RecordError("Invalid PMID")
    return pmid


def canonical_pmcid(value: Any) -> str | None:
    pmcid = _text(value)
    if pmcid is None:
        return None
    pmcid = pmcid.upper()
    if not _PMCID.match(pmcid):
        raise RecordError("Invalid PMCID")
    return pmcid


def licence_code(raw_value: str | None) -> str:
    """Normalise a licence value, failing closed: anything unrecognised is `other`."""
    if raw_value is None:
        return "unknown"
    value = raw_value.strip().lower()
    if not value:
        return "unknown"
    value = _LICENCE_VERSION.sub("", value)
    value = re.sub(r"[\s_]+", "-", value)
    if value in {"cc0", "cc-0", "cc-zero"}:
        return "cc0"
    return value if value in LICENCE_CODES and value.startswith("cc-") else "other"


def relation_type(raw_type: str) -> str:
    value = re.sub(r"\s+", "_", raw_type.strip().lower())
    return value if value in RELATION_TYPES and value != "other" else "other"


def _date(value: Any) -> date | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise RecordError("Invalid date") from exc


def _publication_types(record: dict[str, Any]) -> list[str]:
    pub_types = (record.get("pubTypeList") or {}).get("pubType") or []
    if isinstance(pub_types, str):
        pub_types = [pub_types]
    if not isinstance(pub_types, list):
        raise RecordError("Invalid publication types")
    return [t for t in (_text(p) for p in pub_types) if t]


def _journal(record: dict[str, Any]) -> str | None:
    journal = (record.get("journalInfo") or {}).get("journal") or {}
    if not isinstance(journal, dict):
        return None
    return _text(journal.get("title"))


def _relations(record: dict[str, Any]) -> list[Relation]:
    items = (record.get("commentCorrectionList") or {}).get("commentCorrection") or []
    if isinstance(items, dict):
        items = [items]
    relations: dict[tuple[str, str, str], Relation] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_type = _text(item.get("type"))
        target_source = _text(item.get("source"))
        target_id = _text(item.get("id"))
        if raw_type and target_source and target_id:
            relation = Relation(relation_type(raw_type), raw_type, target_source, target_id)
            relations[(raw_type, target_source, target_id)] = relation
    return list(relations.values())


def normalise(record: dict[str, Any]) -> ArticleValues:
    if not isinstance(record, dict):
        raise RecordError("Record is not an object")
    doi = canonical_doi(record.get("doi"))
    pmid = canonical_pmid(record.get("pmid"))
    pmcid = canonical_pmcid(record.get("pmcid"))
    if doi is None and pmid is None and pmcid is None:
        raise RecordError("Record has no DOI, PMID or PMCID")
    title = _text(record.get("title"))
    if title is None:
        raise RecordError("Record has no title")
    raw_licence = _text(record.get("license"))
    return ArticleValues(
        doi=doi,
        pmid=pmid,
        pmcid=pmcid,
        title=title,
        abstract=_text(record.get("abstractText")),
        authors=_text(record.get("authorString")),
        journal=_journal(record),
        publication_types=_publication_types(record),
        language=_text(record.get("language")),
        published_on=_date(record.get("firstPublicationDate")),
        first_indexed_on=_date(record.get("firstIndexDate")),
        source_record=record,
        licence=Licence(raw_value=raw_licence, licence_code=licence_code(raw_licence)),
        relations=_relations(record),
    )


def record_id(record: Any) -> str | None:
    """The source's ID for logging a failed record, if it can be read."""
    if isinstance(record, dict):
        for key in ("id", "pmid", "pmcid", "doi"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:200]
    return None
