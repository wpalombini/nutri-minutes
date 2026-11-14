"""The Extractor baseline check blocks a pull request on any sign error, on more than ten failed
papers, on a fall in main effects or stated limits beyond the
allowed margin, and on a stale baseline."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evals.abstracts import read_dataset
from evals.extractor.__main__ import DATASET, main
from evals.extractor.baseline import (
    BASELINE,
    MAX_FAILED,
    baseline_data,
    check,
    read_baseline,
    write_baseline,
)
from evals.extractor.run import PaperResult, Scores, approved_rows, labels_hash, score
from tests.extractor_helpers import extractor_prompt

LABELS = "0123456789abcdef"


def scores(
    wrong: int = 0,
    missed: int = 0,
    signs: int = 0,
    no_limit: int = 0,
    failed: int = 0,
    papers: int = 20,
) -> Scores:
    """`papers` papers with a main effect and a stated limit, the first ones answered wrongly."""
    results = []
    right: dict[str, Any] = {
        "measure": "mean_difference",
        "effect_right": True,
        "effect_found_right": True,
        "limitation": True,
        "calls": 1,
    }
    for n in range(papers):
        answer = dict(right)
        if n < failed:
            answer = {"calls": 3, "error": "bad quote"}
        elif n < failed + wrong:
            answer["effect_right"] = False
        elif n < failed + wrong + missed:
            answer.update(measure="none", effect_right=False, effect_found_right=False)
        elif n < failed + wrong + missed + signs:
            answer.update(effect_right=False, sign_error=True)
        elif n < failed + wrong + missed + signs + no_limit:
            answer["limitation"] = False
        results.append(PaperResult(str(n), "mean_difference", True, False, True, **answer))
    return score(results)


def baseline(**kwargs: int) -> dict[str, Any]:
    return {"labels_hash": LABELS, "scores": vars(scores(**kwargs))}


def test_a_run_like_the_baseline_passes() -> None:
    assert check(scores(wrong=1, no_limit=2), LABELS, baseline(wrong=1, no_limit=2)) == []


def test_any_sign_error_blocks() -> None:
    for base in (0, 1):
        problems = check(scores(signs=1), LABELS, baseline(signs=base))
        assert any("1 main effects with the wrong sign: " in p for p in problems)
    assert not [p for p in check(scores(), LABELS, baseline()) if "sign" in p]


def test_more_than_ten_failed_papers_block_whatever_the_baseline() -> None:
    def failures(run: int, base: int) -> list[str]:
        return [
            p for p in check(scores(failed=run), LABELS, baseline(failed=base)) if "failed" in p
        ]

    assert failures(MAX_FAILED, 0) == []
    assert failures(MAX_FAILED + 1, 0) == ["11 papers failed, more than the 10 allowed"]
    assert failures(MAX_FAILED + 1, MAX_FAILED + 1) == [
        "11 papers failed, more than the 10 allowed"
    ]


def test_main_effects_right_may_fall_ten_points() -> None:
    assert check(scores(wrong=2), LABELS, baseline()) == []
    assert check(scores(wrong=3), LABELS, baseline()) == [
        "Main effects right fell to 85.0%, more than 10% below the baseline's 100.0%"
    ]


def test_main_effects_found_may_fall_ten_points() -> None:
    problems = check(scores(missed=3), LABELS, baseline())
    assert any(p.startswith("Main effects found fell to 85.0%") for p in problems)


def test_stated_limits_found_may_fall_fifteen_points() -> None:
    assert check(scores(no_limit=3), LABELS, baseline()) == []
    assert check(scores(no_limit=4), LABELS, baseline()) == [
        "Stated limits found fell to 80.0%, more than 15% below the baseline's 100.0%"
    ]


@pytest.mark.parametrize(("run", "labels"), [(scores(papers=21), LABELS), (scores(), "relabelled")])
def test_a_dataset_change_makes_the_baseline_stale(run: Scores, labels: str) -> None:
    problems = check(run, labels, baseline())
    assert len(problems) == 1
    assert "--write-baseline" in problems[0]


def test_baseline_round_trips_without_facts_or_quotes(tmp_path: Path) -> None:
    prompt = extractor_prompt(tmp_path)
    paper = PaperResult(
        "1",
        "none",
        False,
        False,
        True,
        measure="mean_difference",
        effect_quote="quotes the abstract",
        facts=("result: also quotes it",),
    )
    data = baseline_data(prompt, score([paper]), Decimal("0.0150"), LABELS)
    path = tmp_path / "out" / "baseline.json"
    write_baseline(path, data)
    assert read_baseline(path) == json.loads(json.dumps(data))
    assert "quotes" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"scores": vars(scores())},
        {"labels_hash": LABELS, "scores": {"papers": 56}},
        {"labels_hash": LABELS, "scores": {**vars(scores()), "limitation_found": None}},
        {"labels_hash": LABELS, "scores": {**vars(scores()), "failed": None}},
    ],
)
def test_read_baseline_rejects_other_json(tmp_path: Path, data: object) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="not an Extractor eval baseline"):
        read_baseline(path)


def test_committed_baseline_matches_the_dataset_and_holds_scores_only() -> None:
    data = read_baseline(BASELINE)
    rows = approved_rows(read_dataset(DATASET))
    with_effect = sum(row["expected"]["measure"] != "none" for row in rows)
    assert (data["scores"]["papers"], data["scores"]["with_effect"]) == (len(rows), with_effect)
    assert data["labels_hash"] == labels_hash(rows)
    assert set(data) == {"prompt", "prompt_version", "model", "cost_usd", "labels_hash", "scores"}


@pytest.mark.parametrize("flag", ["--check", "--write-baseline"])
def test_check_and_write_need_every_paper(flag: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([flag, "--limit", "5"])
    assert exc.value.code == 2


def test_check_and_write_are_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(["--check", "--write-baseline"])
