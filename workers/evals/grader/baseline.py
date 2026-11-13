"""The committed Evidence Grader eval baseline, and the check that blocks a pull request on a
regression.

CI runs the eval on pull requests that change the Grader prompt, the Grader, the model client or
the evals, and fails when any rule below breaks. The baseline holds the scores only, never the
model's reasons, which may quote abstracts that can't be reused.

- Any study in people called an animal or lab study, or the reverse (`mixups`). Readers would
  see the wrong kind of evidence.
- More than `MAX_FAILED` failed calls, since a failed paper drops out of the level scores.
- The design label score, or the share of levels within one, falls more than `MAX_FALL` below
  the baseline, or the share of exact levels more than `MAX_EXACT_FALL`. Exact agreement varies
  more between runs, so it gets more room.

A dataset change makes the baseline stale, which the check also reports: refresh it with
`--write-baseline` in the same pull request.
"""

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from evals.abstracts import write_text_atomically
from evals.grader.run import Scores
from pipeline.models import Prompt

BASELINE = Path(__file__).resolve().parent / "baseline.json"
MAX_MIXUPS = 0
MAX_FAILED = 2
MAX_FALL = 0.10
MAX_EXACT_FALL = 0.15
_EPSILON = 1e-9
"""Scores are rounded to four places, so compare with a little slack."""
_SHARES = (
    ("design_label", "Design labels right", MAX_FALL),
    ("level_within_one", "Levels within one", MAX_FALL),
    ("level_exact", "Levels exact", MAX_EXACT_FALL),
)


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
    scores = data.get("scores") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or not isinstance(scores, dict)
        or not all(isinstance(scores.get(key), int) for key in ("papers", "gradable"))
        or not all(isinstance(scores.get(key), float | int) for key, _, _ in _SHARES)
    ):
        # A baseline missing a score would silently switch its rule off.
        raise ValueError(f"{path} is not a Grader eval baseline")
    return data


def check(scores: Scores, baseline: dict[str, Any]) -> list[str]:
    """Why this run should block the pull request. Empty when it passes."""
    problems: list[str] = []
    base = baseline["scores"]
    if (base.get("papers"), base.get("gradable")) != (scores.papers, scores.gradable):
        problems.append(
            f"The baseline scored {base.get('papers')} papers ({base.get('gradable')} gradable), "
            f"this run {scores.papers} ({scores.gradable}). Refresh it with --write-baseline."
        )
    if scores.mixups > MAX_MIXUPS:
        problems.append(
            f"{scores.mixups} studies in people and animal or lab studies mixed up: "
            f"{', '.join(scores.mixup_pmids)}"
        )
    if scores.failed > MAX_FAILED:
        problems.append(f"{scores.failed} calls failed, more than the {MAX_FAILED} allowed")
    for key, name, allowed in _SHARES:
        value, base_value = getattr(scores, key), base[key]
        if value is not None and value < base_value - allowed - _EPSILON:
            problems.append(
                f"{name} fell to {value:.1%}, more than {allowed:.0%} below the baseline's "
                f"{base_value:.1%}"
            )
    return problems
