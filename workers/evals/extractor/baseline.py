"""The committed Extractor eval baseline, and the check that blocks a pull request on a
regression.

CI runs the eval on pull requests that change the Extractor prompt, the Extractor, the model
client or the evals, and fails when any rule below breaks. The baseline holds the scores only,
never extracted facts or quotes, which may come from abstracts that can't be reused.

- Any sign error. Readers would see the result reversed.
- More than `MAX_FAILED` failed papers. Production fails those articles, and they get no summary.
  Four runs of the shipped prompt failed 5 to 8 of 56.
- The share of main effects right, or found, falls more than `MAX_FALL` below the baseline, or
  the share of stated limits found more than `MAX_LIMITATION_FALL`. Absolute numbers are
  reported only: with 5 papers, one paper moves the share by 20 points.

A dataset change makes the baseline stale, which the check also reports: refresh it with
`--write-baseline` in the same pull request. The labels hash catches a relabel that keeps the
counts.
"""

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from evals.abstracts import write_text_atomically
from evals.extractor.run import Scores
from pipeline.models import Prompt

BASELINE = Path(__file__).resolve().parent / "baseline.json"
MAX_FAILED = 10
MAX_FALL = 0.10
MAX_LIMITATION_FALL = 0.15
_EPSILON = 1e-9
"""Scores are rounded to four places, so compare with a little slack."""
_SHARES = (
    ("effect_right", "Main effects right", MAX_FALL),
    ("effect_found", "Main effects found", MAX_FALL),
    ("limitation_found", "Stated limits found", MAX_LIMITATION_FALL),
)
_COUNTS = ("papers", "with_effect", "with_absolute", "with_limitation")


def baseline_data(prompt: Prompt, scores: Scores, cost_usd: Decimal, labels: str) -> dict[str, Any]:
    return {
        "prompt": prompt.name,
        "prompt_version": prompt.version,
        "model": prompt.model,
        "cost_usd": str(cost_usd),
        "labels_hash": labels,
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
        or not isinstance(data.get("labels_hash"), str)
        or not isinstance(scores, dict)
        or not all(isinstance(scores.get(key), int) for key in (*_COUNTS, "failed", "sign_errors"))
        or not all(isinstance(scores.get(key), float | int) for key, _, _ in _SHARES)
    ):
        # A baseline missing a score would silently switch its rule off.
        raise ValueError(f"{path} is not an Extractor eval baseline")
    return data


def check(scores: Scores, labels: str, baseline: dict[str, Any]) -> list[str]:
    """Why this run should block the pull request. Empty when it passes."""
    problems: list[str] = []
    base = baseline["scores"]
    counts = tuple(getattr(scores, key) for key in _COUNTS)
    if tuple(base.get(key) for key in _COUNTS) != counts or baseline["labels_hash"] != labels:
        problems.append(
            "The dataset's labels changed since the baseline was written. "
            "Refresh it with --write-baseline."
        )
    if scores.sign_errors:
        problems.append(
            f"{scores.sign_errors} main effects with the wrong sign: "
            f"{', '.join(scores.sign_error_pmids)}"
        )
    if scores.failed > MAX_FAILED:
        problems.append(f"{scores.failed} papers failed, more than the {MAX_FAILED} allowed")
    for key, name, allowed in _SHARES:
        value, base_value = getattr(scores, key), base[key]
        if value is not None and value < base_value - allowed - _EPSILON:
            problems.append(
                f"{name} fell to {value:.1%}, more than {allowed:.0%} below the baseline's "
                f"{base_value:.1%}"
            )
    return problems
