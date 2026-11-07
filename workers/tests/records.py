"""Synthetic Europe PMC records shaped like `resultType=core` results.

They are made up rather than recorded, so no third-party abstracts are committed.
"""

from typing import Any


def record(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "40000001",
        "source": "MED",
        "pmid": "40000001",
        "pmcid": "PMC9000001",
        "doi": "10.1000/example.1",
        "title": "Protein intake and muscle strength in older adults: a randomised trial.",
        "authorString": "Smith A, Jones B.",
        "abstractText": "Synthetic abstract for tests.",
        "journalInfo": {"journal": {"title": "Journal of Examples"}},
        "pubTypeList": {"pubType": ["Randomized Controlled Trial", "Journal Article"]},
        "language": "eng",
        "license": "cc by",
        "firstPublicationDate": "2026-10-30",
        "firstIndexDate": "2026-11-01",
    }
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


def search_body(records: list[dict[str, Any]], next_cursor: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "version": "6.9",
        "hitCount": len(records),
        "resultList": {"result": records},
    }
    if next_cursor is not None:
        body["nextCursorMark"] = next_cursor
    return body
