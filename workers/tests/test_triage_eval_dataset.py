"""The Triage eval dataset is well formed (`evals/triage/README.md` describes it)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from pipeline.db.models import TOPIC_SLUGS

DATASET = Path(__file__).resolve().parents[1] / "evals" / "triage" / "dataset.jsonl"
REQUIRED = {
    "pmid",
    "doi",
    "pmcid",
    "title",
    "publication_types",
    "licence",
    "sample",
    "expected",
    "label",
    "unsure",
    "note",
}
OPTIONAL = {"abstract"}
ABSTRACT_LICENCES = {"cc-by", "cc0"}
"""Licences whose abstracts may be stored in the repo."""


def _rows() -> list[dict[str, Any]]:
    lines = DATASET.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


ROWS = _rows()


def _id(row: dict[str, Any]) -> str:
    return f"pmid {row.get('pmid')}"


def test_dataset_has_rows() -> None:
    assert ROWS


def test_identifiers_are_unique() -> None:
    pmids = [row["pmid"] for row in ROWS]
    dois = [row["doi"].lower() for row in ROWS if row["doi"]]
    assert len(pmids) == len(set(pmids))
    assert len(dois) == len(set(dois))


@pytest.mark.parametrize("row", ROWS, ids=_id)
def test_row_fields(row: dict[str, Any]) -> None:
    assert REQUIRED <= row.keys() <= REQUIRED | OPTIONAL
    assert isinstance(row["pmid"], str) and re.fullmatch(r"[1-9][0-9]*", row["pmid"])
    assert row["doi"] is None or (isinstance(row["doi"], str) and row["doi"].startswith("10."))
    assert row["pmcid"] is None or re.fullmatch(r"PMC[0-9]+", row["pmcid"])
    assert isinstance(row["title"], str) and row["title"].strip()
    types = row["publication_types"]
    assert isinstance(types, list) and all(isinstance(t, str) for t in types)
    assert isinstance(row["licence"], str) and row["licence"]
    assert row["sample"] in {"random", "picked"}
    assert row["label"] in {"suggested", "approved"}
    assert isinstance(row["unsure"], bool)
    assert isinstance(row["note"], str)
    if row["unsure"]:
        assert row["note"].strip(), "an unsure label needs a note"


@pytest.mark.parametrize("row", ROWS, ids=_id)
def test_expected_decision_is_consistent(row: dict[str, Any]) -> None:
    expected = row["expected"]
    assert set(expected) == {"in_scope", "topics", "primary_topic"}
    assert isinstance(expected["in_scope"], bool)
    topics = expected["topics"]
    assert isinstance(topics, list)
    if expected["in_scope"]:
        assert topics, "an in-scope paper needs at least one topic"
        assert len(topics) == len(set(topics))
        assert set(topics) <= set(TOPIC_SLUGS)
        assert expected["primary_topic"] == topics[0]
    else:
        assert topics == []
        assert expected["primary_topic"] is None


def test_abstracts_only_for_open_licences() -> None:
    for row in ROWS:
        if "abstract" in row:
            assert row["licence"] in ABSTRACT_LICENCES, _id(row)
            assert isinstance(row["abstract"], str) and row["abstract"].strip(), _id(row)
