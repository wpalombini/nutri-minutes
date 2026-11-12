"""The committed Triage eval baseline, and the check that blocks a pull request on a regression.

CI runs the eval on pull requests that change the prompt, the model client, Triage or the evals,
and fails when either rule below breaks. The baseline holds the scores only, never the model's
reasons, which may quote abstracts that can't be reused.

- More than `MAX_MISSED` in-scope papers missed. Missing an in-scope paper is the costlier
  mistake. Haiku misses 0 or 1 between runs of the same prompt, so 2 leaves a margin for that.
  A failed call counts as a miss, so an outage that fails more than 2 in-scope calls blocks too.
- The share of out-of-scope papers dropped falls more than `MAX_DROPPED_FALL` below the
  baseline, so a change can't quietly start keeping almost everything.

A dataset change makes the baseline stale, which the check also reports: refresh it with
`--write-baseline` in the same pull request.
"""

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from evals.abstracts import write_text_atomically
from evals.triage.run import Scores
from pipeline.models import Prompt

BASELINE = Path(__file__).resolve().parent / "baseline.json"
MAX_MISSED = 2
MAX_DROPPED_FALL = 0.10
_EPSILON = 1e-9
"""Scores are rounded to four places, so compare with a little slack."""


def baseline_data(prompt: Prompt, scores: Scores, cost_usd: Decimal) -> dict[str, Any]:
    return {
        "prompt": prompt.name,
        "prompt_version": prompt.version,
        "model": prompt.model,
        "cost_usd": str(cost_usd),
        "scores": asdict(scores),
    }


def write_baseline(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomically(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_baseline(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a Triage eval baseline")
    scores = data.get("scores")
    if (
        not isinstance(scores, dict)
        or not all(isinstance(scores.get(key), int) for key in ("in_scope", "out_of_scope"))
        or not isinstance(scores.get("dropped_out_of_scope"), float | int)
    ):
        # A baseline missing a score would silently switch its rule off.
        raise ValueError(f"{path} is not a Triage eval baseline")
    return data


def check(scores: Scores, baseline: dict[str, Any]) -> list[str]:
    """Why this run should block the pull request. Empty when it passes."""
    problems: list[str] = []
    base = baseline["scores"]
    if (base.get("in_scope"), base.get("out_of_scope")) != (scores.in_scope, scores.out_of_scope):
        problems.append(
            f"The baseline scored {base.get('in_scope')} in-scope and "
            f"{base.get('out_of_scope')} out-of-scope papers, this run {scores.in_scope} and "
            f"{scores.out_of_scope}. Refresh it with --write-baseline."
        )
    if scores.missed > MAX_MISSED:
        problems.append(
            f"{scores.missed} in-scope papers missed, more than the {MAX_MISSED} allowed: "
            f"{', '.join(scores.missed_pmids)}"
        )
    dropped, base_dropped = scores.dropped_out_of_scope, base["dropped_out_of_scope"]
    if dropped is not None and dropped < base_dropped - MAX_DROPPED_FALL - _EPSILON:
        problems.append(
            f"Out-of-scope papers dropped fell to {dropped:.1%}, more than "
            f"{MAX_DROPPED_FALL:.0%} below the baseline's {base_dropped:.1%}"
        )
    return problems
