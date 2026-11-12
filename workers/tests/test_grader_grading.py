"""Turning the model's reading into a grade: starting points, caps, funding and reply checks."""

from typing import Any

import pytest

from pipeline.grader.grading import (
    Grade,
    NotGradable,
    ReplyError,
    level_from,
    parse_reply,
)
from tests.grader_helpers import graded, move, not_gradable


def _grade(**overrides: Any) -> Grade:
    result = parse_reply(graded(**overrides))
    assert isinstance(result, Grade)
    assert result.level == level_from(result.starting_level, result.reasons)
    return result


@pytest.mark.parametrize(
    ("overrides", "start"),
    [
        ({"design_category": "randomised_trial"}, 4),
        ({"design_category": "non_randomised_trial"}, 2),
        ({"design_category": "observational"}, 2),
        ({"design_category": "animal"}, 1),
        ({"design_category": "lab"}, 1),
        ({"design_category": "review", "review_includes": "randomised_trials"}, 4),
        ({"design_category": "review", "review_includes": "observational"}, 2),
        ({"design_category": "review", "review_includes": "mixed"}, 2),
        ({"design_category": "review", "review_includes": "animal_or_lab"}, 1),
        (
            {
                "design_category": "review",
                "review_includes": "randomised_trials",
                "review_reported_level": 2,
            },
            2,
        ),
    ],
)
def test_starting_levels(overrides: dict[str, Any], start: int) -> None:
    assert _grade(moves=[], **overrides).starting_level == start


def test_moves_down_and_floor() -> None:
    assert _grade().level == 3
    grade = _grade(moves=[move("design", levels=2), move("size", levels=2)])
    assert grade.level == 1


def test_raises_are_capped_at_one_level() -> None:
    grade = _grade(
        design_category="observational",
        moves=[move("design", "raises", 2), move("size", "raises", 1)],
    )
    assert grade.level == 3
    assert [r.levels for r in grade.reasons] == [1]


def test_trials_never_go_above_high() -> None:
    grade = _grade(moves=[move("size", "raises", 1)])
    assert grade.level == 4 and grade.reasons == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"design_category": "animal"},
        {"design_category": "lab"},
        {"design_category": "review", "review_includes": "animal_or_lab"},
        {
            "design_category": "review",
            "review_includes": "animal_or_lab",
            "review_reported_level": 2,
        },
    ],
)
def test_animal_and_lab_never_move_up(overrides: dict[str, Any]) -> None:
    grade = _grade(moves=[move("size", "raises", 1), move("design")], **overrides)
    assert grade.level == max(1, grade.starting_level - 1)
    assert [(r.factor, r.direction) for r in grade.reasons] == [("design", "lowers")]


def test_a_review_reporting_its_certainty_is_not_raised() -> None:
    grade = _grade(
        design_category="review",
        review_includes="observational",
        review_reported_level=2,
        moves=[move("design", "raises", 1)],
    )
    assert grade.level == 2 and grade.reasons == ()


def test_review_fields_are_dropped_for_other_designs() -> None:
    grade = _grade(review_includes="mixed", review_reported_level=3)
    assert (grade.review_includes, grade.review_reported_level) == (None, None)


def test_sponsor_running_the_analysis_lowers_one_level() -> None:
    grade = _grade(
        moves=[],
        funder_type="industry",
        funder_sells_product="yes",
        sponsor_roles=["analysis"],
        funding_concern="Funded by the maker of the supplement, which also ran the analysis.",
    )
    assert grade.funding_lowered and grade.level == 3
    assert [(r.factor, r.levels) for r in grade.reasons] == [("funding_and_conflicts", 1)]


@pytest.mark.parametrize(
    "risk",
    [{"outcome_switched": "yes"}, {"registered": "no"}, {"surrogate_outcome": True}],
)
def test_industry_funding_with_a_risk_lowers(risk: dict[str, Any]) -> None:
    grade = _grade(funder_type="industry", funding_concern="Industry funded.", **risk)
    assert grade.funding_lowered and grade.level == 2


def test_several_risks_lower_only_one_level() -> None:
    grade = _grade(
        funder_type="industry",
        funder_sells_product="yes",
        sponsor_roles=["analysis", "writing"],
        outcome_switched="yes",
        registered="no",
        surrogate_outcome=True,
        funding_concern="Funded by the maker.",
    )
    assert grade.level == 2


def test_a_funding_concern_without_a_risk_is_listed_only() -> None:
    grade = _grade(funder_type="industry", funding_concern="Industry funded.")
    assert not grade.funding_lowered and grade.level == 3
    assert grade.reasons[-1].levels == 0


def test_a_risk_without_a_funding_concern_does_not_lower() -> None:
    assert not _grade(surrogate_outcome=True, registered="no").funding_lowered


def test_unregistered_counts_only_for_trials() -> None:
    grade = _grade(
        design_category="observational",
        moves=[],
        funder_type="industry",
        registered="no",
        funding_concern="Industry funded.",
    )
    assert not grade.funding_lowered


def test_a_risk_already_counted_is_not_counted_again() -> None:
    grade = _grade(
        funder_type="industry",
        surrogate_outcome=True,
        funding_risks_counted_elsewhere=True,
        funding_concern="Industry funded.",
    )
    assert not grade.funding_lowered


@pytest.mark.parametrize(
    "statement",
    [
        "None",
        "None declared.",
        "No conflicts of interest",
        "The authors declare no competing interests.",
        "no conflict of interest was declared",
        "Nothing to disclose",
        "N/A",
        "The authors declare no competing financial interests.",
        "The authors declare that they have no conflicts of interest.",
        "There are no conflicts of interest.",
        "No relevant conflicts of interest.",
    ],
)
def test_no_conflicts_statements_are_not_a_concern(statement: str) -> None:
    grade = _grade(conflicts=statement, surrogate_outcome=True)
    assert grade.funding.conflicts is None and not grade.funding_lowered


@pytest.mark.parametrize(
    "statement",
    [
        "Author A is paid by a dairy council; the others declare no conflicts.",
        "No conflicts, except A consults for a food company.",
        "None, but B owns shares in the sponsor.",
        "No. A received fees from a supplement maker.",
    ],
)
def test_declared_conflicts_are_kept_even_beside_no_conflicts(statement: str) -> None:
    grade = _grade(conflicts=statement, surrogate_outcome=True, funding_concern="A conflict.")
    assert grade.funding.conflicts == statement and grade.funding_lowered


def test_funding_not_stated_is_kept() -> None:
    grade = _grade(funder=None, funder_type="not_stated", funding_source="not_stated")
    assert grade.funding.funding_source == "not_stated"


def test_not_gradable() -> None:
    assert parse_reply(not_gradable("protocol")) == NotGradable(
        "protocol", "An overview without a systematic search."
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"reason": " "}, "no reason"),
        ({"not_gradable": "case_report"}, "reason it isn't gradable"),
        ({"gradable": False, "not_gradable": "none"}, "not_gradable"),
        ({"design_category": "none"}, "design_category"),
        ({"design_category": "review", "review_includes": "none"}, "review_includes"),
        ({"main_outcome": ""}, "main outcome"),
        ({"participants": 0}, "participants"),
        ({"funder_type": "not_stated"}, "disagree"),
        ({"funding_source": "not_stated"}, "disagree"),
        ({"moves": [move("size", text=" ")]}, "no text"),
        ({"moves": [move("funding_and_conflicts")]}, "factor"),
        (
            {
                "funder_type": "industry",
                "funder_sells_product": "yes",
                "sponsor_roles": ["writing"],
            },
            "funding_concern",
        ),
    ],
)
def test_replies_that_make_no_sense(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ReplyError, match=message):
        parse_reply(graded(**overrides))
