"""The baseline check blocks a pull request on more than two missed in-scope papers, or on a fall
of more than ten points in out-of-scope papers dropped."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from evals.abstracts import read_dataset
from evals.triage.__main__ import DATASET, main
from evals.triage.baseline import (
    BASELINE,
    MAX_MISSED,
    baseline_data,
    check,
    read_baseline,
    write_baseline,
)
from evals.triage.run import PaperResult, Scores, approved_rows, score
from tests.triage_helpers import triage_prompt


def scores(missed: int, wrongly_kept: int, in_scope: int = 10, out_of_scope: int = 10) -> Scores:
    results = [
        PaperResult(f"i{n}", True, ("bone-health",), in_scope=n >= missed, topics=("bone-health",))
        for n in range(in_scope)
    ] + [PaperResult(f"o{n}", False, (), in_scope=n < wrongly_kept) for n in range(out_of_scope)]
    return score(results)


def baseline(wrongly_kept: int = 2) -> dict[str, object]:
    return {"scores": {"in_scope": 10, "out_of_scope": 10, **_dropped(wrongly_kept)}}


def _dropped(wrongly_kept: int) -> dict[str, float | None]:
    return {"dropped_out_of_scope": scores(0, wrongly_kept).dropped_out_of_scope}


def test_up_to_two_missed_papers_pass() -> None:
    assert check(scores(MAX_MISSED, 2), baseline()) == []


def test_three_missed_papers_block() -> None:
    problems = check(scores(MAX_MISSED + 1, 2), baseline())
    assert len(problems) == 1
    assert "3 in-scope papers missed" in problems[0]
    assert "i0, i1, i2" in problems[0]


def test_out_of_scope_dropped_may_fall_ten_points() -> None:
    # Baseline drops 80%: 70% passes, 60% blocks.
    assert check(scores(0, 3), baseline(2)) == []
    problems = check(scores(0, 4), baseline(2))
    assert len(problems) == 1
    assert "fell to 60.0%" in problems[0]


def test_a_better_run_passes() -> None:
    assert check(scores(0, 0), baseline(5)) == []


def test_a_dataset_change_makes_the_baseline_stale() -> None:
    problems = check(scores(0, 2, in_scope=11), baseline())
    assert len(problems) == 1
    assert "--write-baseline" in problems[0]


def test_baseline_round_trips_without_reasons(tmp_path: Path) -> None:
    prompt = triage_prompt(tmp_path)
    result = PaperResult("1", True, ("bone-health",), in_scope=True, reason="quotes the abstract")
    data = baseline_data(prompt, score([result]), Decimal("0.0461"))
    path = tmp_path / "out" / "baseline.json"
    write_baseline(path, data)
    assert read_baseline(path) == json.loads(json.dumps(data))
    assert "quotes the abstract" not in path.read_text(encoding="utf-8")
    assert data["prompt_version"] == prompt.version


def test_read_baseline_rejects_other_json(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"papers": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a Triage eval baseline"):
        read_baseline(path)


def test_committed_baseline_matches_the_dataset_and_holds_scores_only() -> None:
    data = read_baseline(BASELINE)
    rows = approved_rows(read_dataset(DATASET))
    in_scope = sum(row["expected"]["in_scope"] for row in rows)
    assert (data["scores"]["in_scope"], data["scores"]["out_of_scope"]) == (
        in_scope,
        len(rows) - in_scope,
    )
    assert set(data) == {"prompt", "prompt_version", "model", "cost_usd", "scores"}
    assert data["scores"]["missed"] <= MAX_MISSED


@pytest.mark.parametrize("flag", ["--check", "--write-baseline"])
def test_check_and_write_need_every_paper(flag: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([flag, "--limit", "5"])
    assert exc.value.code == 2


def test_check_and_write_are_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(["--check", "--write-baseline"])
