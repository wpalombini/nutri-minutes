"""The Grader's rules and design checks against publication types."""

import pytest

from pipeline.grader.rules import GraderArticle, apply_rules, design_conflict
from pipeline.grader.run import grant_agencies, prompt_inputs


def _article(*types: str) -> GraderArticle:
    return GraderArticle(1, "A title", "An abstract.", types, ())


@pytest.mark.parametrize(
    ("types", "expected"),
    [
        (("Case Reports",), "case_report"),
        (("case-report", "Journal Article"), "case_report"),
        (("Clinical Trial Protocol",), "protocol"),
        (("Journal Article",), None),
        (("Review",), None),
        (("Case Reports", "Systematic Review"), None),
        (("Clinical Trial Protocol", "Randomized Controlled Trial"), None),
    ],
)
def test_rules(types: tuple[str, ...], expected: str | None) -> None:
    decision = apply_rules(_article(*types))
    assert (decision.not_gradable if decision else None) == expected


@pytest.mark.parametrize(
    ("types", "design", "conflict"),
    [
        (("Randomized Controlled Trial",), "animal", True),
        (("Clinical Trial",), "lab", True),
        (("Randomized Controlled Trial",), "observational", False),
        (("Meta-Analysis",), "observational", True),
        (("Systematic Review",), "review", False),
        (("Review",), "observational", False),
        (("Journal Article",), "animal", False),
    ],
)
def test_design_conflicts(types: tuple[str, ...], design: str, conflict: bool) -> None:
    assert (design_conflict(_article(*types), design) is not None) is conflict


def test_grant_agencies_are_deduplicated_and_capped() -> None:
    grants = {
        "grant": [
            {"agency": "Council A", "grantId": "1"},
            {"agency": " Council A ", "grantId": "2"},
            {"agency": "Charity B"},
            {"grantId": "3"},
            "junk",
        ]
        + [{"agency": f"Funder {n}"} for n in range(20)]
    }
    agencies = grant_agencies(grants)
    assert agencies[:2] == ("Council A", "Charity B")
    assert len(agencies) == 10


@pytest.mark.parametrize("grants", [None, {}, {"grant": "x"}, []])
def test_missing_grants(grants: object) -> None:
    assert grant_agencies(grants) == ()


def test_prompt_inputs_say_when_nothing_is_listed() -> None:
    inputs = prompt_inputs(GraderArticle(1, "T", "A", (), ()))
    assert inputs["grant_agencies"] == "none listed"
    assert inputs["publication_types"] == "not given"
