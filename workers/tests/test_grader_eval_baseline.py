"""The Grader baseline check blocks a pull request on any people versus animal or lab mix-up, on
more than two failed calls, and on a fall in design labels or levels beyond the allowed margin."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evals.abstracts import read_dataset
from evals.grader.__main__ import DATASET, main
from evals.grader.baseline import (
    BASELINE,
    MAX_FAILED,
    MAX_MIXUPS,
    baseline_data,
    check,
    read_baseline,
    write_baseline,
)
from evals.grader.run import PaperResult, Scores, approved_rows, score
from tests.grader_helpers import grader_prompt


def scores(
    wrong_labels: int = 0,
    off_by_one: int = 0,
    off_by_two: int = 0,
    mixups: int = 0,
    failed: int = 0,
    papers: int = 20,
) -> Scores:
    """`papers` randomised trials expected at level 3, the first ones answered wrongly."""
    results = []
    for n in range(papers):
        base = PaperResult(str(n), "randomised_trial", True, 3)
        answer: dict[str, Any] = {"label": "randomised_trial", "in_people": True, "level": 3}
        if n < failed:
            answer = {}
        elif n < failed + mixups:
            answer = {"label": "animal", "in_people": False, "level": 1}
        elif n < failed + mixups + wrong_labels:
            answer = {"label": "observational", "in_people": True, "level": 3}
        elif n < failed + mixups + wrong_labels + off_by_one:
            answer["level"] = 2
        elif n < failed + mixups + wrong_labels + off_by_one + off_by_two:
            answer["level"] = 1
        results.append(PaperResult(**{**vars(base), **answer}))
    return score(results)


def baseline(**kwargs: int) -> dict[str, Any]:
    return {"scores": vars(scores(**kwargs))}


def test_a_run_like_the_baseline_passes() -> None:
    assert check(scores(wrong_labels=1, off_by_one=2), baseline(wrong_labels=1, off_by_one=2)) == []


def test_any_mixup_blocks() -> None:
    problems = check(scores(mixups=MAX_MIXUPS + 1), baseline())
    assert any("mixed up: 0" in p for p in problems)


def test_more_than_two_failed_calls_block() -> None:
    assert not [p for p in check(scores(failed=MAX_FAILED), baseline()) if "failed" in p]
    problems = check(scores(failed=MAX_FAILED + 1), baseline())
    assert any("3 calls failed" in p for p in problems)


def test_design_labels_may_fall_ten_points() -> None:
    # 20 papers: 2 more wrong labels is ten points and passes, 3 blocks.
    assert check(scores(wrong_labels=2), baseline()) == []
    problems = check(scores(wrong_labels=3), baseline())
    assert problems == [
        "Design labels right fell to 85.0%, more than 10% below the baseline's 100.0%"
    ]


def test_levels_within_one_may_fall_ten_points() -> None:
    assert check(scores(off_by_two=2), baseline()) == []
    problems = check(scores(off_by_two=3), baseline())
    assert any(p.startswith("Levels within one fell to 85.0%") for p in problems)


def test_exact_levels_may_fall_fifteen_points() -> None:
    assert check(scores(off_by_one=3), baseline()) == []
    problems = check(scores(off_by_one=4), baseline())
    assert problems == ["Levels exact fell to 80.0%, more than 15% below the baseline's 100.0%"]


def test_a_dataset_change_makes_the_baseline_stale() -> None:
    problems = check(scores(papers=21), baseline())
    assert len(problems) == 1
    assert "--write-baseline" in problems[0]


def test_baseline_round_trips_without_reasons(tmp_path: Path) -> None:
    prompt = grader_prompt(tmp_path)
    paper = PaperResult(
        "1",
        "randomised_trial",
        True,
        3,
        label="randomised_trial",
        level=3,
        reason="quotes the abstract",
        funding_concern="also quotes it",
    )
    data = baseline_data(prompt, score([paper]), Decimal("0.0150"))
    path = tmp_path / "out" / "baseline.json"
    write_baseline(path, data)
    assert read_baseline(path) == json.loads(json.dumps(data))
    assert "quotes" not in path.read_text(encoding="utf-8")
    assert data["prompt_version"] == prompt.version


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"papers": []},
        {"scores": {"papers": 69, "gradable": 56}},
        {"scores": {**vars(scores()), "level_exact": None}},
    ],
)
def test_read_baseline_rejects_other_json(tmp_path: Path, data: object) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="not a Grader eval baseline"):
        read_baseline(path)


def test_committed_baseline_matches_the_dataset_and_holds_scores_only() -> None:
    data = read_baseline(BASELINE)
    rows = approved_rows(read_dataset(DATASET))
    gradable = sum(row["expected"]["gradable"] for row in rows)
    assert (data["scores"]["papers"], data["scores"]["gradable"]) == (len(rows), gradable)
    assert set(data) == {"prompt", "prompt_version", "model", "cost_usd", "scores"}
    assert data["scores"]["mixups"] <= MAX_MIXUPS
    assert data["scores"]["failed"] <= MAX_FAILED


@pytest.mark.parametrize("flag", ["--check", "--write-baseline"])
def test_check_and_write_need_every_paper(flag: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([flag, "--limit", "5"])
    assert exc.value.code == 2


def test_check_and_write_are_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(["--check", "--write-baseline"])
