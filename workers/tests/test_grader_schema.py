"""Constraints and permissions on `evidence_grades` and `evidence_grade_reasons`."""

from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from tests.triage_helpers import insert_article

COLUMNS = (
    "article_id",
    "run_id",
    "decided_by",
    "model_call_id",
    "not_gradable",
    "design_category",
    "review_includes",
    "review_reported_level",
    "starting_level",
    "level",
    "main_outcome",
    "participants",
    "duration",
    "population",
    "funder",
    "funder_type",
    "funding_source",
    "funder_sells_product",
    "sponsor_roles",
    "conflicts",
    "registered",
    "outcome_switched",
    "surrogate_outcome",
    "funding_lowered",
)
# Built from the fixed column names above, never from input.
GRADE = (
    f"INSERT INTO evidence_grades ({', '.join(COLUMNS)}, reason) "  # noqa: S608
    f"VALUES ({', '.join(':' + c for c in COLUMNS)}, 'r') RETURNING id"
)
REASON = (
    "INSERT INTO evidence_grade_reasons (grade_id, position, factor, direction, levels, reason) "
    "VALUES (:grade_id, :position, :factor, :direction, :levels, :reason)"
)


def _setup(conn: Connection) -> dict[str, int]:
    article_id = insert_article(conn, 1)
    run_id = conn.execute(
        text(
            "INSERT INTO pipeline_runs (agent, status, parameters) "
            "VALUES ('grader', 'running', CAST('{}' AS jsonb)) RETURNING id"
        )
    ).scalar_one()
    call_id = conn.execute(
        text(
            "INSERT INTO model_calls (run_id, stage, prompt_name, prompt_version, attempt, "
            "input_values, model_requested, outcome, raw_reply, max_cost_usd) VALUES "
            "(:run_id, 'grader', 'grader/grade', 'v', 1, CAST('{}' AS jsonb), 'm', "
            "'succeeded', '{}', 0) RETURNING id"
        ),
        {"run_id": run_id},
    ).scalar_one()
    return {"article_id": article_id, "run_id": int(run_id), "call_id": int(call_id)}


def _graded(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "article_id": ids["article_id"],
        "run_id": ids["run_id"],
        "decided_by": "model",
        "model_call_id": ids["call_id"],
        "not_gradable": None,
        "design_category": "randomised_trial",
        "review_includes": None,
        "review_reported_level": None,
        "starting_level": 4,
        "level": 3,
        "main_outcome": "Hip bone density",
        "participants": 120,
        "duration": "12 months",
        "population": "Women aged 60 to 75",
        "funder": "A dairy council",
        "funder_type": "industry",
        "funding_source": "abstract",
        "funder_sells_product": "yes",
        "sponsor_roles": ["analysis"],
        "conflicts": None,
        "registered": "yes",
        "outcome_switched": "unknown",
        "surrogate_outcome": True,
        "funding_lowered": True,
    }
    values.update(overrides)
    return values


def _ungraded(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    values = dict.fromkeys(COLUMNS)
    values.update(
        article_id=ids["article_id"],
        run_id=ids["run_id"],
        decided_by="rule",
        not_gradable="case_report",
        sponsor_roles=[],
    )
    values.update(overrides)
    return values


def _review(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    values = _graded(
        ids, design_category="review", review_includes="randomised_trials", starting_level=4
    )
    values.update(overrides)
    return values


VALID: list[tuple[str, dict[str, Any]]] = [
    ("graded", {}),
    ("graded", {"funder_type": "not_stated", "funding_source": "not_stated", "funder": None}),
    ("graded", {"design_category": "observational", "starting_level": 2, "level": 3}),
    ("graded", {"design_category": "non_randomised_trial", "starting_level": 2, "level": 1}),
    ("graded", {"design_category": "animal", "starting_level": 1, "level": 1}),
    ("graded", {"design_category": "lab", "starting_level": 1, "level": 1}),
    ("review", {"level": 4}),
    ("review", {"review_includes": "mixed", "starting_level": 2, "level": 2}),
    ("review", {"review_includes": "observational", "starting_level": 2, "level": 3}),
    ("review", {"review_includes": "animal_or_lab", "starting_level": 1, "level": 1}),
    (
        "review",
        {
            "review_includes": "observational",
            "review_reported_level": 3,
            "starting_level": 3,
            "level": 3,
        },
    ),
    ("graded", {"design_category": "non_randomised_trial", "starting_level": 2, "level": 3}),
    ("graded", {"funding_lowered": False, "surrogate_outcome": False, "sponsor_roles": []}),
    ("graded", {"funding_lowered": True, "surrogate_outcome": False, "registered": "no"}),
    ("graded", {"funding_lowered": True, "surrogate_outcome": False, "outcome_switched": "yes"}),
    ("graded", {"surrogate_outcome": False, "sponsor_roles": ["writing"]}),
    (
        "review",
        {
            "review_includes": "animal_or_lab",
            "review_reported_level": 2,
            "starting_level": 2,
            "level": 2,
        },
    ),
    ("ungraded", {}),
    (
        "ungraded",
        {"decided_by": "model", "model_call_id": "call", "not_gradable": "narrative_review"},
    ),
]


@pytest.mark.parametrize(("kind", "overrides"), VALID)
def test_valid_grades(conn: Connection, kind: str, overrides: dict[str, Any]) -> None:
    ids = _setup(conn)
    if overrides.get("model_call_id") == "call":
        overrides = {**overrides, "model_call_id": ids["call_id"]}
    builder = {"graded": _graded, "ungraded": _ungraded, "review": _review}[kind]
    conn.execute(text(GRADE), builder(ids, **overrides))


INVALID: list[tuple[str, dict[str, Any]]] = [
    ("graded", {"decided_by": "person"}),
    ("graded", {"model_call_id": None}),
    ("graded", {"decided_by": "rule", "model_call_id": None}),
    ("graded", {"design_category": "cohort"}),
    ("graded", {"design_category": None}),
    ("graded", {"main_outcome": None}),
    ("graded", {"funding_lowered": None}),
    ("graded", {"not_gradable": "case_report"}),
    ("graded", {"starting_level": 3}),
    ("graded", {"design_category": "observational", "starting_level": 2, "level": 4}),
    ("graded", {"design_category": "animal", "starting_level": 1, "level": 2}),
    ("graded", {"design_category": "lab", "starting_level": 1, "level": 2}),
    ("graded", {"level": 0}),
    ("graded", {"level": 5}),
    ("graded", {"participants": 0}),
    ("graded", {"funder_type": "pharma"}),
    ("graded", {"funding_source": "not_stated"}),
    ("graded", {"funder_type": "not_stated"}),
    ("graded", {"funder_sells_product": "maybe"}),
    ("graded", {"registered": None}),
    ("graded", {"outcome_switched": "perhaps"}),
    ("graded", {"sponsor_roles": ["analysis", "marketing"]}),
    ("graded", {"review_includes": "randomised_trials"}),
    ("graded", {"review_reported_level": 3}),
    ("review", {"review_includes": None}),
    ("review", {"review_includes": "mixed", "starting_level": 4}),
    ("review", {"review_includes": "animal_or_lab", "starting_level": 1, "level": 2}),
    ("review", {"review_reported_level": 5, "starting_level": 5, "level": 4}),
    ("review", {"review_reported_level": 2, "starting_level": 4}),
    ("graded", {"surrogate_outcome": False, "sponsor_roles": ["design"]}),
    ("graded", {"surrogate_outcome": False, "funder_sells_product": "unknown"}),
    ("graded", {"main_outcome": ""}),
    (
        "review",
        {
            "review_includes": "animal_or_lab",
            "review_reported_level": 2,
            "starting_level": 2,
            "level": 3,
        },
    ),
    ("ungraded", {"not_gradable": None}),
    ("ungraded", {"not_gradable": "editorial"}),
    ("ungraded", {"model_call_id": "call"}),
    ("ungraded", {"level": 2}),
    ("ungraded", {"participants": 10}),
    ("ungraded", {"funder_type": "industry"}),
    ("ungraded", {"sponsor_roles": ["design"]}),
]


@pytest.mark.parametrize(("kind", "overrides"), INVALID)
def test_grade_checks(conn: Connection, kind: str, overrides: dict[str, Any]) -> None:
    ids = _setup(conn)
    if overrides.get("model_call_id") == "call":
        overrides = {**overrides, "model_call_id": ids["call_id"]}
    builder = {"graded": _graded, "ungraded": _ungraded, "review": _review}[kind]
    with pytest.raises(IntegrityError):
        conn.execute(text(GRADE), builder(ids, **overrides))


def _reason(grade_id: int, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "grade_id": grade_id,
        "position": 1,
        "factor": "size",
        "direction": "lowers",
        "levels": 1,
        "reason": "Size: 40 people.",
    }
    values.update(overrides)
    return values


def test_valid_reasons(conn: Connection) -> None:
    grade_id = conn.execute(text(GRADE), _graded(_setup(conn))).scalar_one()
    conn.execute(text(REASON), _reason(grade_id))
    conn.execute(
        text(REASON),
        _reason(grade_id, position=2, factor="funding_and_conflicts", levels=0),
    )
    conn.execute(text(REASON), _reason(grade_id, position=3, direction="raises", levels=2))


@pytest.mark.parametrize(
    "overrides",
    [
        {"position": 0},
        {"factor": "journal"},
        {"direction": "up"},
        {"levels": 3},
        {"levels": -1},
        {"reason": ""},
        {"grade_id": -1},
        {"factor": "funding_and_conflicts", "direction": "raises"},
        {"factor": "funding_and_conflicts", "levels": 2},
    ],
)
def test_reason_checks(conn: Connection, overrides: dict[str, Any]) -> None:
    grade_id = conn.execute(text(GRADE), _graded(_setup(conn))).scalar_one()
    with pytest.raises(IntegrityError):
        conn.execute(text(REASON), {**_reason(grade_id), **overrides})


def test_reason_positions_are_unique(conn: Connection) -> None:
    grade_id = conn.execute(text(GRADE), _graded(_setup(conn))).scalar_one()
    conn.execute(text(REASON), _reason(grade_id))
    with pytest.raises(IntegrityError):
        conn.execute(text(REASON), _reason(grade_id))


def test_one_funding_drop_per_grade(conn: Connection) -> None:
    grade_id = conn.execute(text(GRADE), _graded(_setup(conn))).scalar_one()
    funding = {"factor": "funding_and_conflicts"}
    conn.execute(text(REASON), _reason(grade_id, **funding))
    conn.execute(text(REASON), _reason(grade_id, position=2, levels=0, **funding))
    with pytest.raises(IntegrityError):
        conn.execute(text(REASON), _reason(grade_id, position=3, **funding))


def test_worker_role_can_only_add(conn: Connection) -> None:
    ids = _setup(conn)
    conn.execute(text("SET LOCAL ROLE pipeline_worker"))
    grade_id = conn.execute(text(GRADE), _graded(ids)).scalar_one()
    conn.execute(text(REASON), _reason(grade_id))
    for statement in (
        "UPDATE evidence_grades SET level = 2",
        "DELETE FROM evidence_grades",
        "UPDATE evidence_grade_reasons SET levels = 2",
        "DELETE FROM evidence_grade_reasons",
    ):
        savepoint = conn.begin_nested()
        with pytest.raises(ProgrammingError):
            conn.execute(text(statement))
        savepoint.rollback()
