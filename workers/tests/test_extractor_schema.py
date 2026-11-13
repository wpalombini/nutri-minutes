"""Constraints and permissions on `extractions` and `extraction_facts`."""

from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from tests.test_grader_schema import GRADE, _graded, _setup

COLUMNS = (
    "article_id",
    "run_id",
    "grade_id",
    "model_call_id",
    "source_basis",
    "population",
    "population_quote",
    "intervention",
    "intervention_quote",
    "comparator",
    "comparator_quote",
    "measure",
    "estimate",
    "ci_lower",
    "ci_upper",
    "ci_level",
    "unit",
    "outcome_label",
    "comparison_label",
    "lower_label",
    "higher_label",
    "effect_quote",
)
# Built from the fixed column names above, never from input.
EXTRACTION = (
    f"INSERT INTO extractions ({', '.join(COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join(':' + c for c in COLUMNS)}) RETURNING id"
)
FACT = (
    "INSERT INTO extraction_facts (extraction_id, position, kind, fact, quote) "
    "VALUES (:extraction_id, :position, :kind, :fact, :quote)"
)
NO_EFFECT = {
    "measure": None,
    "estimate": None,
    "ci_lower": None,
    "ci_upper": None,
    "ci_level": None,
    "unit": None,
    "outcome_label": None,
    "comparison_label": None,
    "lower_label": None,
    "higher_label": None,
    "effect_quote": None,
}


def _ids(conn: Connection) -> dict[str, int]:
    ids = _setup(conn)
    ids["grade_id"] = int(conn.execute(text(GRADE), _graded(ids)).scalar_one())
    return ids


def _extraction(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "article_id": ids["article_id"],
        "run_id": ids["run_id"],
        "grade_id": ids["grade_id"],
        "model_call_id": ids["call_id"],
        "source_basis": "abstract",
        "population": "Women aged 60 to 75",
        "population_quote": "120 women aged 60-75 years",
        "intervention": "Daily dairy",
        "intervention_quote": "three servings of dairy daily",
        "comparator": "Usual diet",
        "comparator_quote": "or their usual diet",
        "measure": "hazard_ratio",
        "estimate": "0.91",
        "ci_lower": "0.80",
        "ci_upper": "1.04",
        "ci_level": 95,
        "unit": None,
        "outcome_label": "Hip fracture risk",
        "comparison_label": "Dairy compared with usual diet",
        "lower_label": "Lower risk",
        "higher_label": "Higher risk",
        "effect_quote": "HR 0.91, 95% CI 0.80-1.04",
    }
    values.update(overrides)
    return values


VALID: list[dict[str, Any]] = [
    {},
    NO_EFFECT,
    {"comparator": None, "comparator_quote": None},
    {"source_basis": "full_text"},
    {"ci_lower": None, "ci_upper": None, "ci_level": None},
    {"ci_lower": "0.91"},
    {"ci_upper": "0.91"},
    {"ci_level": 90},
    {
        "measure": "mean_difference",
        "unit": "kg",
        "estimate": "-1.2",
        "ci_lower": "-2.0",
        "ci_upper": "0",
    },
    {
        "measure": "risk_ratio",
        "estimate": "0.91",
        "ci_lower": None,
        "ci_upper": None,
        "ci_level": None,
    },
    {"ci_level": 50},
    {"ci_level": 99},
    {"measure": "mean_difference", "unit": "kg", "estimate": "0.6", "ci_lower": "-0.3"},
    {"measure": "risk_difference", "unit": "percentage points", "estimate": "1.0"},
    {"measure": "standardised_mean_difference", "estimate": "0.95"},
    {"measure": "odds_ratio", "estimate": "12", "ci_lower": "0.9", "ci_upper": "160"},
]


@pytest.mark.parametrize("overrides", VALID)
def test_valid_extractions(conn: Connection, overrides: dict[str, Any]) -> None:
    conn.execute(text(EXTRACTION), _extraction(_ids(conn), **overrides))


def test_numbers_keep_their_precision(conn: Connection) -> None:
    extraction_id = conn.execute(text(EXTRACTION), _extraction(_ids(conn))).scalar_one()
    stored = conn.execute(
        text("SELECT estimate::text, ci_lower::text FROM extractions WHERE id = :id"),
        {"id": extraction_id},
    ).one()
    assert tuple(stored) == ("0.91", "0.80")


INVALID: list[dict[str, Any]] = [
    {"source_basis": "metadata"},
    {"population": ""},
    {"population_quote": ""},
    {"intervention_quote": ""},
    {"comparator_quote": None},
    {"comparator": None},
    {"comparator": ""},
    {"measure": "relative_risk"},
    {"measure": None},
    {**NO_EFFECT, "outcome_label": "Hip fracture risk"},
    {"estimate": None},
    {"outcome_label": None},
    {"comparison_label": None},
    {"lower_label": None},
    {"higher_label": None},
    {"effect_quote": None},
    {"effect_quote": ""},
    {"ci_lower": None},
    {"ci_upper": None},
    {"ci_level": None},
    {"ci_lower": None, "ci_upper": None},
    {"ci_level": 100},
    {"ci_level": 0},
    {"ci_lower": "1.04", "ci_upper": "0.80"},
    {"ci_lower": "0.91", "ci_upper": "0.91"},
    {"estimate": "1.10"},
    {"estimate": "0.70"},
    {
        "measure": "risk_ratio",
        "estimate": "0",
        "ci_lower": None,
        "ci_upper": None,
        "ci_level": None,
    },
    {"measure": "odds_ratio", "estimate": "0.5", "ci_lower": "-0.1"},
    {"measure": "odds_ratio", "estimate": "0.5", "ci_lower": "0"},
    {"unit": "kg"},
    {"measure": "mean_difference", "unit": ""},
    {"measure": "mean_difference", "estimate": "0.6", "ci_lower": "-0.3"},
    {"measure": "risk_difference", "estimate": "1.0"},
    {"ci_level": 49},
    {**NO_EFFECT, "ci_lower": "0.80", "ci_upper": "1.04", "ci_level": 95},
    {**NO_EFFECT, "unit": "kg"},
    {"estimate": "NaN", "ci_lower": None, "ci_upper": None, "ci_level": None},
    {"ci_upper": "Infinity"},
    {"measure": "mean_difference", "unit": "kg", "ci_lower": "-Infinity"},
]


@pytest.mark.parametrize("overrides", INVALID)
def test_extraction_checks(conn: Connection, overrides: dict[str, Any]) -> None:
    ids = _ids(conn)
    with pytest.raises(IntegrityError):
        conn.execute(text(EXTRACTION), _extraction(ids, **overrides))


def test_extraction_needs_a_grade(conn: Connection) -> None:
    ids = {**_ids(conn), "grade_id": -1}
    with pytest.raises(IntegrityError):
        conn.execute(text(EXTRACTION), _extraction(ids))


def _fact(extraction_id: int, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "extraction_id": extraction_id,
        "position": 1,
        "kind": "limitation",
        "fact": "Diet was self-reported",
        "quote": "dietary intake was self-reported",
    }
    values.update(overrides)
    return values


def test_valid_facts(conn: Connection) -> None:
    extraction_id = conn.execute(text(EXTRACTION), _extraction(_ids(conn))).scalar_one()
    for position, kind in enumerate(("outcome", "result", "absolute", "limitation"), start=1):
        conn.execute(text(FACT), _fact(extraction_id, position=position, kind=kind))


@pytest.mark.parametrize(
    "overrides",
    [
        {"position": 0},
        {"kind": "funding"},
        {"fact": ""},
        {"quote": ""},
        {"extraction_id": -1},
    ],
)
def test_fact_checks(conn: Connection, overrides: dict[str, Any]) -> None:
    extraction_id = conn.execute(text(EXTRACTION), _extraction(_ids(conn))).scalar_one()
    with pytest.raises(IntegrityError):
        conn.execute(text(FACT), {**_fact(extraction_id), **overrides})


def test_fact_positions_are_unique(conn: Connection) -> None:
    extraction_id = conn.execute(text(EXTRACTION), _extraction(_ids(conn))).scalar_one()
    conn.execute(text(FACT), _fact(extraction_id))
    with pytest.raises(IntegrityError):
        conn.execute(text(FACT), _fact(extraction_id, kind="result"))


def test_worker_role_can_only_add(conn: Connection) -> None:
    ids = _ids(conn)
    conn.execute(text("SET LOCAL ROLE pipeline_worker"))
    extraction_id = conn.execute(text(EXTRACTION), _extraction(ids)).scalar_one()
    conn.execute(text(FACT), _fact(extraction_id))
    for statement in (
        "UPDATE extractions SET population = 'x'",
        "DELETE FROM extractions",
        "UPDATE extraction_facts SET fact = 'x'",
        "DELETE FROM extraction_facts",
    ):
        savepoint = conn.begin_nested()
        with pytest.raises(ProgrammingError):
            conn.execute(text(statement))
        savepoint.rollback()
