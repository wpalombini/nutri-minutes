"""Turning records into article, licence and relation values."""

from typing import Any

import pytest

from pipeline.scout.normalise import (
    RecordError,
    canonical_doi,
    licence_code,
    normalise,
    record_id,
    relation_type,
)
from tests.records import record


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1000/ABC", "10.1000/abc"),
        ("  doi:10.1000/x ", "10.1000/x"),
        ("DOI: 10.1000/x", "10.1000/x"),
        ("https://doi.org/10.1000/X", "10.1000/x"),
        ("http://dx.doi.org/10.1000/x", "10.1000/x"),
        ("HTTPS://DX.DOI.ORG/10.1000/x", "10.1000/x"),
        ("", None),
        (None, None),
    ],
)
def test_canonical_doi(raw: str | None, expected: str | None) -> None:
    assert canonical_doi(raw) == expected


@pytest.mark.parametrize("raw", ["11.1000/x", "10.1000/has space", "not a doi"])
def test_invalid_doi(raw: str) -> None:
    with pytest.raises(RecordError):
        canonical_doi(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cc by", "cc-by"),
        ("CC BY", "cc-by"),
        ("cc-by 4.0", "cc-by"),
        ("cc by-sa", "cc-by-sa"),
        ("cc by-nc", "cc-by-nc"),
        ("cc by-nd", "cc-by-nd"),
        ("cc by-nc-sa", "cc-by-nc-sa"),
        ("cc by-nc-nd", "cc-by-nc-nd"),
        ("cc0", "cc0"),
        ("CC-0", "cc0"),
        ("cc zero", "cc0"),
        ("CC0 1.0", "cc0"),
        ("public domain", "other"),
        ("cc by-xyz", "other"),
        ("other", "other"),
        ("unknown", "other"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_licence_code_fails_closed(raw: str | None, expected: str) -> None:
    assert licence_code(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Retraction in", "retraction_in"),
        ("Retraction of", "retraction_of"),
        ("Erratum for", "erratum_for"),
        ("Expression of concern for", "expression_of_concern_for"),
        ("Comment on", "comment_on"),
        ("Cites", "other"),
        ("other", "other"),
    ],
)
def test_relation_type(raw: str, expected: str) -> None:
    assert relation_type(raw) == expected


def test_normalise_full_record() -> None:
    values = normalise(
        record(
            commentCorrectionList={
                "commentCorrection": [
                    {"type": "Retraction in", "source": "MED", "id": "40000099"},
                    {"type": "Retraction in", "source": "MED", "id": "40000099"},
                    {"type": "Comment in", "source": "MED"},
                ]
            }
        )
    )
    assert values.doi == "10.1000/example.1"
    assert values.pmid == "40000001"
    assert values.pmcid == "PMC9000001"
    assert values.journal == "Journal of Examples"
    assert values.publication_types == ["Randomized Controlled Trial", "Journal Article"]
    assert values.authors == "Smith A, Jones B."
    assert values.published_on is not None and values.published_on.isoformat() == "2026-10-30"
    assert values.licence.raw_value == "cc by"
    assert values.licence.licence_code == "cc-by"
    assert [(r.relation_type, r.target_id) for r in values.relations] == [
        ("retraction_in", "40000099")
    ]


def test_missing_licence_is_unknown() -> None:
    values = normalise(record(license=None))
    assert values.licence.raw_value is None
    assert values.licence.licence_code == "unknown"


def test_single_publication_type_as_string() -> None:
    values = normalise(record(pubTypeList={"pubType": "Review"}))
    assert values.publication_types == ["Review"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"doi": None, "pmid": None, "pmcid": None},
        {"title": None},
        {"title": "   "},
        {"pmid": "abc"},
        {"pmcid": "12345"},
        {"firstIndexDate": "2026-13-01"},
        {"title": 42},
        {"pubTypeList": ["Review"]},
        {"journalInfo": "Journal of Examples"},
        {"journalInfo": {"journal": "Journal of Examples"}},
        {"commentCorrectionList": ["Retraction in"]},
        {"commentCorrectionList": {"commentCorrection": "Retraction in"}},
    ],
)
def test_invalid_records(overrides: dict[str, Any]) -> None:
    with pytest.raises(RecordError):
        normalise(record(**overrides))


def test_record_id() -> None:
    assert record_id(record()) == "40000001"
    assert record_id({"doi": "10.1000/x"}) == "10.1000/x"
    assert record_id("not a record") is None


def test_nul_characters_are_stripped() -> None:
    values = normalise(record(title="A study\x00 of diet", abstractText="Text\x00"))
    assert values.title == "A study of diet"
    assert values.abstract == "Text"
    assert values.source_record["title"] == "A study of diet"


def test_non_object_record() -> None:
    with pytest.raises(RecordError):
        normalise(["not", "a", "record"])
