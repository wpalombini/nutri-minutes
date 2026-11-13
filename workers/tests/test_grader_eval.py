"""The Grader eval scores design labels and levels, through production's rules and reply checks."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evals.grader.__main__ import summary
from evals.grader.run import PaperResult, approved_rows, report, run_eval, score
from pipeline.models import BudgetExceeded, CallRequest, ModelCallError
from pipeline.models.fake import FakeModelClient
from tests.grader_helpers import graded, grader_prompt, move, not_gradable
from tests.prompt_files import write_prompt


def row(
    pmid: str,
    design: str | None = "randomised_trial",
    level: int | None = 3,
    *,
    not_gradable: str | None = None,
    includes: str | None = None,
    types: tuple[str, ...] = ("Journal Article",),
    label: str = "approved",
) -> dict[str, Any]:
    gradable = design is not None
    return {
        "pmid": pmid,
        "title": f"Study {pmid}",
        "publication_types": list(types),
        "grant_agencies": ["A research council"],
        "label": label,
        "expected": {
            "gradable": gradable,
            "not_gradable": not_gradable,
            "design_category": design,
            "review_includes": includes,
            "review_reported_level": None,
            "level": level if gradable else None,
        },
    }


def result(pmid: str, label: str, expected: str = "randomised_trial", **fields: Any) -> PaperResult:
    people = fields.pop("expected_in_people", expected not in ("animal", "lab"))
    level = fields.pop("expected_level", 3)
    return PaperResult(pmid, expected, people, level, label=label, **fields)


def test_score_counts_labels_mixups_and_levels() -> None:
    results = [
        result("0", "randomised_trial", level=3, in_people=True),
        result("1", "randomised_trial", level=2, in_people=True),
        result("2", "observational", level=1, in_people=True),
        result("3", "animal", level=1, in_people=False),
        result("4", "animal", "animal", expected_level=1, level=1, in_people=False),
        result(
            "5",
            "narrative_review",
            "narrative_review",
            expected_in_people=None,
            expected_level=None,
        ),
        result("6", "not_a_study"),
    ]
    scores = score(results)
    assert (scores.papers, scores.gradable, scores.failed) == (7, 6, 0)
    assert scores.wrong_label_pmids == ("2", "3", "6")
    assert scores.design_label == round(4 / 7, 4)
    assert scores.mixup_pmids == ("3",)
    assert scores.level_scored == 5
    assert scores.level_exact == round(2 / 5, 4)
    assert scores.level_within_one == round(3 / 5, 4)
    assert scores.off_by_two_pmids == ("2", "3")


def test_not_gradable_is_no_mixup_and_failed_calls_count_as_wrong_labels() -> None:
    scores = score(
        [
            PaperResult("1", "animal", False, 1, label="not_a_study"),
            PaperResult("2", "observational", True, 2, error="boom"),
        ]
    )
    assert scores.mixups == 0
    assert scores.failed == 1
    assert scores.design_label == 0.0
    assert scores.level_scored == 0
    assert scores.level_exact is None


def test_reviews_of_animal_studies_are_not_in_people() -> None:
    scores = score([PaperResult("1", "review", False, 1, label="review", in_people=True)])
    assert scores.mixup_pmids == ("1",)


def test_only_approved_rows_count() -> None:
    rows = [row("1"), row("2", label="suggested")]
    assert [r["pmid"] for r in approved_rows(rows)] == ["1"]


def test_run_eval_follows_production_rules_and_replies(tmp_path: Path) -> None:
    prompt = grader_prompt(tmp_path)

    def respond(request: CallRequest) -> dict[str, Any] | Exception:
        title = request.inputs["title"]
        if title == "Study 3":
            return ModelCallError("no provider")
        if title == "Study 4":
            return not_gradable()
        return graded()

    client = FakeModelClient(respond)
    rows = [
        row("1"),
        row("2", None, not_gradable="case_report", types=("Case Reports",)),
        row("3", "observational", 1),
        row("4", None, not_gradable="narrative_review"),
    ]
    abstracts = {pmid: f"Abstract {pmid}." for pmid in "1234"}
    seen: list[tuple[int, int]] = []
    results = run_eval(client, prompt, rows, abstracts, lambda d, t: seen.append((d, t)))

    assert client.requests[0].inputs == {
        "title": "Study 1",
        "abstract": "Abstract 1.",
        "publication_types": "Journal Article",
        "grant_agencies": "A research council",
    }
    assert len(client.requests) == 3, "the case report is decided by a rule, with no call"
    assert (results[0].label, results[0].level, results[0].in_people) == (
        "randomised_trial",
        3,
        True,
    )
    assert (results[1].label, results[1].decided_by) == ("case_report", "rule")
    assert results[2].failed and results[2].error == "no provider"
    assert (results[3].label, results[3].decided_by) == ("narrative_review", "model")
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]
    scores = score(results)
    assert scores.decided_by_rule == 1
    assert scores.design_label == 0.75


def test_a_design_that_contradicts_the_publication_types_fails_the_paper(tmp_path: Path) -> None:
    prompt = grader_prompt(tmp_path)
    client = FakeModelClient(lambda _: graded(design_category="animal", moves=[]))
    rows = [row("1", types=("Randomized Controlled Trial",))]
    results = run_eval(client, prompt, rows, {"1": "A."})
    assert len(client.requests) == 3
    assert results[0].failed


def test_funding_concerns_that_only_say_no_conflicts_are_counted(tmp_path: Path) -> None:
    prompt = grader_prompt(tmp_path)
    replies = {
        "Study 1": graded(funding_concern="The authors report no competing interests."),
        "Study 2": graded(
            funder_type="industry",
            funding_concern="Funded by a dairy company that sells the product.",
            moves=[move("size")],
        ),
        "Study 3": graded(),
        "Study 4": graded(
            funder_type="industry",
            funding_concern="Industry funded it; the authors declare no conflicts.",
        ),
    }
    client = FakeModelClient(lambda request: replies[request.inputs["title"]])
    rows = [row("1"), row("2"), row("3"), row("4")]
    results = run_eval(client, prompt, rows, {p: "A." for p in "1234"})
    scores = score(results)
    assert scores.funding_concerns == 3
    assert scores.no_conflicts_concern_pmids == ("1",)
    assert results[1].funding_lowered is False


def test_a_stopped_run_stops_the_eval(tmp_path: Path) -> None:
    prompt = grader_prompt(tmp_path)
    client = FakeModelClient(lambda _: BudgetExceeded("spent"))
    with pytest.raises(BudgetExceeded):
        run_eval(client, prompt, [row("1")], {"1": "A."})


def test_run_eval_needs_a_grader_prompt(tmp_path: Path) -> None:
    other = write_prompt(tmp_path, "triage/scope")
    with pytest.raises(ValueError, match="grader prompt"):
        run_eval(FakeModelClient(lambda _: {}), other, [], {})


def test_report_and_summary_hold_no_abstracts(tmp_path: Path) -> None:
    prompt = grader_prompt(tmp_path)
    results = run_eval(
        FakeModelClient(lambda _: graded()), prompt, [row("1")], {"1": "Secret abstract."}
    )
    scores = score(results)
    data = report(prompt, scores, results, Decimal("0.0150"))
    assert "Secret abstract." not in json.dumps(data)
    assert data["scores"]["level_exact"] == 1.0
    assert data["cost_usd"] == "0.0150"
    lines = summary(prompt.model, scores, Decimal("0.0150"))
    assert "Design labels right: 100.0%" in lines
    assert "exact 100.0%, within one 100.0%" in lines
