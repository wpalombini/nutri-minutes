"""The Extractor eval scores main effects and facts, through production's prompt inputs and reply
checks."""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from evals.abstracts import read_dataset
from evals.extractor.__main__ import DATASET, summary
from evals.extractor.run import (
    PaperResult,
    approved_rows,
    article,
    compare,
    labels_hash,
    report,
    run_eval,
    score,
    unit_form,
)
from pipeline.extractor.extraction import Extraction, Fact, MainEffect
from pipeline.extractor.run import PROMPT_NAME, _article, prompt_inputs
from pipeline.models import BudgetExceeded, CallRequest, ModelCallError, load_prompt
from pipeline.models.fake import FakeModelClient
from tests.extractor_helpers import ABSTRACT, NO_EFFECT, extracted, extractor_prompt
from tests.prompt_files import write_prompt

HAZARD = {
    "measure": "hazard_ratio",
    "estimate": "0.80",
    "ci_lower": "0.65",
    "ci_upper": "0.97",
    "ci_level": "95",
    "unit": None,
}
NONE = {key: None for key in HAZARD} | {"measure": "none"}


def row(
    pmid: str,
    effect: dict[str, Any] | None = None,
    *,
    also: list[dict[str, Any]] | None = None,
    absolute: bool = True,
    limitation: bool = True,
    label: str = "approved",
) -> dict[str, Any]:
    return {
        "pmid": pmid,
        "title": f"Study {pmid}",
        "publication_types": ["Randomized Controlled Trial"],
        "grader": {
            "design_category": "randomised_trial",
            "review_includes": None,
            "main_outcome": "hip fracture",
            "participants": 1200,
            "duration": "3 years",
            "population": "women aged 65 or older",
        },
        "expected": {
            **(HAZARD if effect is None else effect),
            "has_absolute": absolute,
            "has_limitation": limitation,
        },
        "also_accepted": also or [],
        "label": label,
    }


def effect(measure: str = "hazard_ratio", estimate: str = "0.80", **fields: Any) -> MainEffect:
    values: dict[str, Any] = {
        "ci_lower": Decimal("0.65"),
        "ci_upper": Decimal("0.97"),
        "ci_level": Decimal("95"),
        "unit": None,
    }
    values.update(fields)
    return MainEffect(
        measure=measure,
        estimate=Decimal(estimate),
        outcome_label="o",
        comparison_label="c",
        lower_label="l",
        higher_label="h",
        quote="q",
        **values,
    )


def extraction(main: MainEffect | None, *kinds: str) -> Extraction:
    return Extraction(
        population="p",
        population_quote="p",
        intervention="i",
        intervention_quote="i",
        comparator=None,
        comparator_quote=None,
        effect=main,
        facts=tuple(Fact(kind, "f", "q") for kind in kinds),
    )


def base(expected: dict[str, Any] = HAZARD, absolute: bool = False) -> PaperResult:
    return PaperResult("1", expected["measure"], expected["measure"] != "none", absolute, False)


def targets(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return list(items)


def test_the_expected_effect_is_right_when_every_number_is_written_the_same() -> None:
    result = compare(base(), targets(HAZARD), extraction(effect(), "absolute"))
    assert (result.effect_right, result.effect_found_right, result.sign_error) == (
        True,
        True,
        False,
    )
    assert (result.estimate, result.ci_level, result.absolute) == ("0.80", "95", True)
    wrong = compare(base(), targets(HAZARD), extraction(effect(estimate="0.8")))
    assert (wrong.effect_right, wrong.effect_found_right) == (False, True)


def test_an_alternative_constrains_only_the_fields_it_gives() -> None:
    other = effect("odds_ratio", "3.26", ci_lower=None, ci_upper=None, ci_level=None)
    alternatives = targets(HAZARD, {"measure": "odds_ratio", "estimate": "3.26"})
    assert compare(base(), alternatives, extraction(other)).effect_right
    any_odds = targets(HAZARD, {"measure": "odds_ratio"})
    assert compare(base(), any_odds, extraction(effect("odds_ratio", "9.9"))).effect_right


def test_no_effect_is_right_only_when_a_label_says_so() -> None:
    assert compare(base(NONE), targets(NONE), extraction(None)).effect_right
    missed = compare(base(), targets(HAZARD), extraction(None))
    assert (missed.effect_right, missed.effect_found_right, missed.measure) == (
        False,
        False,
        "none",
    )
    allowed = compare(base(), targets(HAZARD, {"measure": "none"}), extraction(None))
    assert allowed.effect_right and allowed.effect_found_right


def test_an_estimate_with_the_opposite_sign_is_a_sign_error() -> None:
    expected = {**NONE, "measure": "mean_difference", "estimate": "-4.17", "unit": "days"}
    result = compare(
        base(expected),
        targets(expected),
        extraction(effect("mean_difference", "4.17", ci_lower=None, ci_upper=None, ci_level=None)),
    )
    assert result.sign_error and not result.effect_right
    zero = {**expected, "estimate": "0.00"}
    same = effect("mean_difference", "0.00", ci_lower=None, ci_upper=None, ci_level=None)
    assert not compare(base(zero), targets(zero), extraction(same)).sign_error


def test_units_are_compared_loosely_and_only_when_the_label_gives_one() -> None:
    expected = {**HAZARD, "measure": "mean_difference", "unit": "kg/m²"}
    main = effect("mean_difference", "0.80", unit="KG / m2")
    assert compare(base(expected), targets(expected), extraction(main)).unit_right is True
    other = compare(
        base(expected), targets(expected), extraction(effect("mean_difference", "0.80", unit="kg"))
    )
    assert other.unit_right is False
    loose = {"measure": "mean_difference", "estimate": "0.80"}
    assert compare(base(expected), targets(loose), extraction(main)).unit_right is None
    assert unit_form(" ") is None


def test_score_counts_effects_signs_facts_and_failures() -> None:
    results = [
        compare(base(absolute=True), targets(HAZARD), extraction(effect(), "absolute")),
        compare(base(absolute=True), targets(HAZARD), extraction(None)),
        compare(base(NONE), targets(NONE), extraction(effect(), "absolute")),
        compare(base(), targets(HAZARD), extraction(effect(estimate="0.81"))),
        PaperResult("5", "none", False, False, True, calls=3, error="bad quote"),
    ]
    results = [PaperResult(**{**vars(r), "pmid": str(n)}) for n, r in enumerate(results, 1)]
    scores = score(results)
    assert (scores.papers, scores.with_effect, scores.failed) == (5, 3, 1)
    assert scores.effect_right == 0.2
    assert scores.effect_found == 0.4
    assert scores.missed_effect_pmids == ("2",)
    assert scores.extra_effect_pmids == ("3",)
    assert scores.wrong_effect_pmids == ("4",)
    assert scores.failed_pmids == ("5",)
    assert (scores.with_absolute, scores.absolute_found, scores.absolute_extra) == (2, 0.5, 1)
    assert (scores.with_limitation, scores.limitation_found) == (1, 0.0)
    assert (scores.calls, scores.asked_again) == (3, 1)


def test_only_approved_rows_count_and_a_relabel_changes_the_hash() -> None:
    rows = [row("1"), row("2", label="suggested")]
    assert [r["pmid"] for r in approved_rows(rows)] == ["1"]
    relabelled = [row("1", {**HAZARD, "estimate": "0.81"})]
    assert labels_hash(rows[:1]) != labels_hash(relabelled)
    assert labels_hash(rows[:1]) == labels_hash([row("1")])


def test_run_eval_follows_production_inputs_and_checks(tmp_path: Path) -> None:
    prompt = extractor_prompt(tmp_path)
    replies: dict[str, list[dict[str, Any] | Exception]] = {
        "Study 1": [extracted()],
        "Study 2": [extracted(effect_quote="not in the abstract"), extracted()],
        "Study 3": [extracted(effect_quote="not in the abstract")] * 3,
        "Study 4": [ModelCallError("no provider")],
        "Study 5": [extracted(**NO_EFFECT)],
    }

    def respond(request: CallRequest) -> dict[str, Any] | Exception:
        return replies[request.inputs["title"]].pop(0)

    client = FakeModelClient(respond)
    rows = [row(str(n)) for n in range(1, 5)] + [row("5", NONE)]
    seen: list[tuple[int, int]] = []
    results = run_eval(
        client,
        prompt,
        rows,
        {str(n): ABSTRACT for n in range(1, 6)},
        lambda d, t: seen.append((d, t)),
    )
    assert client.requests[0].inputs == {
        "title": "Study 1",
        "abstract": ABSTRACT,
        "publication_types": "Randomized Controlled Trial",
        "design": "randomised trial",
        "main_outcome": "hip fracture",
        "participants": "1200",
        "duration": "3 years",
        "population": "women aged 65 or older",
        "check_failure": "",
    }
    assert [r.calls for r in results] == [1, 2, 3, 1, 1]
    assert [r.effect_right for r in results] == [True, True, False, False, True]
    assert results[2].failed and "quote" in (results[2].error or "")
    assert results[3].error == "no provider"
    assert results[0].absolute and results[0].limitation
    assert seen[-1] == (5, 5)


def test_a_stopped_run_stops_the_eval(tmp_path: Path) -> None:
    prompt = extractor_prompt(tmp_path)
    client = FakeModelClient(lambda _: BudgetExceeded("spent"))
    with pytest.raises(BudgetExceeded):
        run_eval(client, prompt, [row("1")], {"1": ABSTRACT})


def test_run_eval_needs_an_extractor_prompt(tmp_path: Path) -> None:
    other = write_prompt(tmp_path, "triage/scope")
    with pytest.raises(ValueError, match="extractor prompt"):
        run_eval(FakeModelClient(lambda _: {}), other, [], {})


def test_report_and_summary_hold_no_abstracts(tmp_path: Path) -> None:
    prompt = extractor_prompt(tmp_path)
    secret = ABSTRACT + " Secret sentence."
    results = run_eval(FakeModelClient(lambda _: extracted()), prompt, [row("1")], {"1": secret})
    scores = score(results)
    data = report(prompt, scores, results, Decimal("0.0150"))
    assert "Secret sentence." not in json.dumps(data)
    assert data["scores"]["effect_right"] == 1.0
    lines = summary(prompt.model, scores, Decimal("0.0150"))
    assert "Main effects right: 100.0%" in lines
    assert "($0.01500 per paper)" in lines


@pytest.mark.parametrize(
    "dataset_row", approved_rows(read_dataset(DATASET)), ids=lambda r: r["pmid"]
)
def test_dataset_rows_render_as_production_renders_a_grade(dataset_row: dict[str, Any]) -> None:
    """The eval's inputs from the dataset's `grader` fields are the ones production builds from a
    grade row, and the shipped prompt accepts them (#79 review)."""
    grader = dataset_row["grader"]
    database_row = SimpleNamespace(
        id=1,
        title=dataset_row["title"],
        abstract="An abstract.",
        publication_types=dataset_row["publication_types"],
        grade_id=1,
        **grader,
    )
    production = prompt_inputs(_article(database_row))
    assert prompt_inputs(article(dataset_row, "An abstract.")) == production
    load_prompt(PROMPT_NAME).render(production)
