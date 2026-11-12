"""The Evidence Grader eval dataset is well formed (`evals/grader/README.md` describes it)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from pipeline.db.models import (
    DESIGN_CATEGORIES,
    LICENCE_CODES,
    NOT_GRADABLE_REASONS,
    REUSABLE_LICENCE_CODES,
    REVIEW_INCLUDES,
)
from pipeline.grader.grading import starting_level

DATASET = Path(__file__).resolve().parents[1] / "evals" / "grader" / "dataset.jsonl"
REQUIRED = {
    "pmid",
    "doi",
    "pmcid",
    "title",
    "publication_types",
    "grant_agencies",
    "licence",
    "sample",
    "expected",
    "label",
    "unsure",
    "note",
}
OPTIONAL = {"abstract", "reviewed_by"}
EXPECTED = {
    "gradable",
    "not_gradable",
    "design_category",
    "review_includes",
    "review_reported_level",
    "level",
}


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
    for key in ("publication_types", "grant_agencies"):
        assert isinstance(row[key], list) and all(isinstance(t, str) for t in row[key])
    assert row["licence"] in LICENCE_CODES
    assert row["sample"] in {"stratified", "picked"}
    assert row["label"] in {"suggested", "approved"}
    if row["label"] == "approved":
        assert row.get("reviewed_by") in {"owner", "owner-rule", "agreement", "reconciled"}
    else:
        assert "reviewed_by" not in row
    assert isinstance(row["unsure"], bool)
    assert isinstance(row["note"], str) and row["note"].strip()


@pytest.mark.parametrize("row", ROWS, ids=_id)
def test_expected_grade_is_consistent(row: dict[str, Any]) -> None:
    expected = row["expected"]
    assert set(expected) == EXPECTED
    if not expected["gradable"]:
        assert expected["not_gradable"] in NOT_GRADABLE_REASONS
        assert all(expected[k] is None for k in EXPECTED - {"gradable", "not_gradable"})
        return
    assert expected["gradable"] is True and expected["not_gradable"] is None
    design = expected["design_category"]
    assert design in DESIGN_CATEGORIES
    includes, reported = expected["review_includes"], expected["review_reported_level"]
    if design == "review":
        assert includes in REVIEW_INCLUDES
        assert reported is None or reported in (1, 2, 3, 4)
    else:
        assert includes is None and reported is None
    level = expected["level"]
    assert level in (1, 2, 3, 4)
    start = starting_level(design, includes, reported)
    assert level <= start + 1
    if design in ("animal", "lab") or includes == "animal_or_lab" or reported is not None:
        assert level <= start


def test_abstracts_only_for_open_licences() -> None:
    for row in ROWS:
        if "abstract" in row:
            assert row["licence"] in REUSABLE_LICENCE_CODES, _id(row)
            assert isinstance(row["abstract"], str) and row["abstract"].strip(), _id(row)
