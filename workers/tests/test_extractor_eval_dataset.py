"""The Extractor eval dataset is well formed (`evals/extractor/README.md` describes it)."""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pipeline.db.models import (
    DESIGN_CATEGORIES,
    EFFECT_MEASURES,
    LICENCE_CODES,
    RATIO_MEASURES,
    REUSABLE_LICENCE_CODES,
    REVIEW_INCLUDES,
)
from pipeline.extractor.extraction import NO_MEASURE, appears

DATASET = Path(__file__).resolve().parents[1] / "evals" / "extractor" / "dataset.jsonl"
GRADER_DATASET = Path(__file__).resolve().parents[1] / "evals" / "grader" / "dataset.jsonl"
REQUIRED = {
    "pmid",
    "doi",
    "pmcid",
    "title",
    "publication_types",
    "licence",
    "grader",
    "grader_source",
    "expected",
    "also_accepted",
    "label",
    "unsure",
    "note",
}
OPTIONAL = {"abstract", "reviewed_by"}
GRADER = {
    "design_category",
    "review_includes",
    "main_outcome",
    "participants",
    "duration",
    "population",
}
EFFECT = ("measure", "estimate", "ci_lower", "ci_upper", "ci_level", "unit")
EXPECTED = {*EFFECT, "has_absolute", "has_limitation"}
NUMBER = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)")
DIFFERENCES_WITH_UNIT = ("mean_difference", "risk_difference")


def _rows(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


ROWS = _rows(DATASET)


def _id(row: dict[str, Any]) -> str:
    return f"pmid {row.get('pmid')}"


def test_dataset_has_rows() -> None:
    assert ROWS


def test_identifiers_are_unique() -> None:
    pmids = [row["pmid"] for row in ROWS]
    assert len(pmids) == len(set(pmids))


def test_papers_are_the_graders_gradable_papers() -> None:
    gradable = {r["pmid"] for r in _rows(GRADER_DATASET) if r["expected"]["gradable"]}
    assert {row["pmid"] for row in ROWS} == gradable


@pytest.mark.parametrize("row", ROWS, ids=_id)
def test_row_fields(row: dict[str, Any]) -> None:
    assert REQUIRED <= row.keys() <= REQUIRED | OPTIONAL
    assert isinstance(row["pmid"], str) and re.fullmatch(r"[1-9][0-9]*", row["pmid"])
    assert row["doi"] is None or (isinstance(row["doi"], str) and row["doi"].startswith("10."))
    assert row["pmcid"] is None or re.fullmatch(r"PMC[0-9]+", row["pmcid"])
    assert isinstance(row["title"], str) and row["title"].strip()
    assert isinstance(row["publication_types"], list)
    assert all(isinstance(t, str) for t in row["publication_types"])
    assert row["licence"] in LICENCE_CODES
    assert row["label"] in {"suggested", "approved"}
    if row["label"] == "approved":
        assert row.get("reviewed_by") in {"owner", "owner-rule", "agreement", "reconciled"}
    else:
        assert "reviewed_by" not in row
    assert isinstance(row["unsure"], bool)
    assert isinstance(row["note"], str) and row["note"].strip()


@pytest.mark.parametrize("row", ROWS, ids=_id)
def test_grader_inputs(row: dict[str, Any]) -> None:
    grader = row["grader"]
    assert set(grader) == GRADER
    assert row["grader_source"] in {"production", "hand"}
    design = grader["design_category"]
    assert design in DESIGN_CATEGORIES
    if design == "review":
        assert grader["review_includes"] in REVIEW_INCLUDES
    else:
        assert grader["review_includes"] is None
    assert isinstance(grader["main_outcome"], str) and grader["main_outcome"].strip()
    participants = grader["participants"]
    assert participants is None or (isinstance(participants, int) and participants > 0)
    for key in ("duration", "population"):
        assert grader[key] is None or (isinstance(grader[key], str) and grader[key].strip())


def _check_effect(effect: dict[str, Any]) -> None:
    """An effect has the shape `extractions` stores, with numbers as strings."""
    measure = effect["measure"]
    if measure == NO_MEASURE:
        assert all(effect.get(key) is None for key in EFFECT[1:])
        return
    assert measure in EFFECT_MEASURES
    numbers = {}
    for key in ("estimate", "ci_lower", "ci_upper", "ci_level"):
        value = effect.get(key)
        assert value is None or (isinstance(value, str) and NUMBER.fullmatch(value)), key
        numbers[key] = None if value is None else Decimal(value)
    estimate = numbers["estimate"]
    lower, upper, level = numbers["ci_lower"], numbers["ci_upper"], numbers["ci_level"]
    unit = effect.get("unit")
    if estimate is None:
        # Only an alternative may leave the numbers open: any estimate of that measure counts.
        assert lower is None and upper is None and level is None
    if lower is not None or upper is not None or level is not None:
        assert lower is not None and upper is not None and level is not None
        assert Decimal(50) <= level < Decimal(100)
        assert lower < upper
        assert estimate is None or lower <= estimate <= upper
    if measure in RATIO_MEASURES:
        assert unit is None
        assert estimate is None or estimate > 0
        assert lower is None or lower > 0
    elif measure in DIFFERENCES_WITH_UNIT:
        assert isinstance(unit, str) and unit.strip()


@pytest.mark.parametrize("row", ROWS, ids=_id)
def test_expected_effect_is_consistent(row: dict[str, Any]) -> None:
    expected = row["expected"]
    assert set(expected) == EXPECTED
    assert isinstance(expected["has_absolute"], bool)
    assert isinstance(expected["has_limitation"], bool)
    _check_effect(expected)
    if expected["measure"] != NO_MEASURE:
        assert expected["estimate"] is not None


@pytest.mark.parametrize("row", ROWS, ids=_id)
def test_also_accepted_effects(row: dict[str, Any]) -> None:
    alternatives = row["also_accepted"]
    assert isinstance(alternatives, list)
    for alternative in alternatives:
        assert "measure" in alternative and set(alternative) <= set(EFFECT)
        _check_effect(alternative)
        assert alternative != {k: v for k, v in row["expected"].items() if k in alternative}


def test_abstracts_only_for_open_licences() -> None:
    for row in ROWS:
        if "abstract" in row:
            assert row["licence"] in REUSABLE_LICENCE_CODES, _id(row)
            assert isinstance(row["abstract"], str) and row["abstract"].strip(), _id(row)


def test_effect_numbers_are_in_stored_abstracts() -> None:
    """Each expected number appears, without its sign, in the abstract when the row stores it."""
    for row in ROWS:
        if "abstract" not in row:
            continue
        for effect in (row["expected"], *row["also_accepted"]):
            for key in ("estimate", "ci_lower", "ci_upper", "ci_level"):
                value = effect.get(key)
                if value is not None:
                    assert appears(value.removeprefix("-"), row["abstract"]), (_id(row), key)
