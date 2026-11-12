"""Run the Triage eval: `python -m evals.triage`.

Needs `OPENROUTER_API_KEY`, and `EUROPE_PMC_CONTACT` when an abstract isn't stored or cached yet.
Prints the scores. `--report PATH` also writes every paper's decision as JSON, and
`--prompt-root DIR` runs a candidate prompt from `DIR/triage/scope.{md,json}` instead of the
shipped one, to compare models without editing it. `--check` compares the scores with the
committed baseline and `--write-baseline` replaces it (`baseline.py` has the rules). Exits 1 if
the eval couldn't finish, such as when it hits its budget or an abstract can't be found, and 2 if
`--check` finds a regression.
"""

import argparse
import json
import logging
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from evals.abstracts import AbstractCache, AbstractError, default_cache_dir, read_dataset
from evals.abstracts import resolve_abstracts as resolve
from evals.triage.baseline import BASELINE, baseline_data, check, read_baseline, write_baseline
from evals.triage.run import EVAL_RUN_ID, Scores, approved_rows, report, run_eval, score
from pipeline.models import PromptError, StopRun, load_prompt
from pipeline.models.calls import MemoryCallLog
from pipeline.models.openrouter import OpenRouterClient, OpenRouterSettings
from pipeline.triage.run import PROMPT_NAME, STAGE

DATASET = Path(__file__).resolve().parent / "dataset.jsonl"
DEFAULT_BUDGET_USD = Decimal("0.50")
"""Enough for one pass over the dataset on a cheap model, with retries."""


def _budget(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation:
        amount = Decimal(-1)
    if not amount.is_finite() or amount <= 0:
        raise argparse.ArgumentTypeError(f"not a budget in US dollars: {value!r}")
    return amount


def _limit(value: str) -> int:
    number = int(value) if value.isdigit() else 0
    if number < 1:
        raise argparse.ArgumentTypeError(f"not a number of papers: {value!r}")
    return number


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def summary(model: str, scores: Scores, cost: Decimal) -> str:
    lines = [
        f"Model: {model}",
        f"Papers: {scores.papers} ({scores.in_scope} in scope, {scores.out_of_scope} out)",
        f"In-scope papers kept: {_percent(scores.kept_in_scope)} "
        f"({scores.missed} missed: {', '.join(scores.missed_pmids) or 'none'})",
        f"Out-of-scope papers dropped: {_percent(scores.dropped_out_of_scope)} "
        f"({scores.wrongly_kept} kept)",
        f"Accuracy: {_percent(scores.accuracy)}",
        f"Primary topic among expected topics: {_percent(scores.primary_topic_listed)}, "
        f"same as expected primary: {_percent(scores.primary_topic_exact)}",
        f"Failed calls: {scores.failed}",
        f"Cost: ${cost:.4f}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.triage", description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET, help=argparse.SUPPRESS)
    parser.add_argument("--prompt-root", type=Path, help="a folder holding triage/scope.{md,json}")
    parser.add_argument("--budget", type=_budget, default=DEFAULT_BUDGET_USD, help="US dollars")
    parser.add_argument("--limit", type=_limit, help="score only the first N approved papers")
    parser.add_argument("--report", type=Path, help="write every decision to this JSON file")
    parser.add_argument("--baseline", type=Path, default=BASELINE, help=argparse.SUPPRESS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail on a regression from the baseline")
    mode.add_argument("--write-baseline", action="store_true", help="replace the baseline")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if (args.check or args.write_baseline) and args.limit is not None:
        parser.error("--check and --write-baseline need every approved paper, not --limit")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

    try:
        prompt = load_prompt(PROMPT_NAME, args.prompt_root)
        settings = OpenRouterSettings.from_env()
        baseline = read_baseline(args.baseline) if args.check else None
    except (PromptError, RuntimeError, OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    rows = approved_rows(read_dataset(args.dataset))[: args.limit]
    try:
        abstracts = resolve(rows, AbstractCache(default_cache_dir()))
    except AbstractError as exc:
        print(exc, file=sys.stderr)
        return 1

    def progress(done: int, total: int) -> None:
        if sys.stderr.isatty():
            print(f"\r{done}/{total}", end="" if done < total else "\n", file=sys.stderr)

    log = MemoryCallLog()
    with OpenRouterClient(settings, log=log, budgets={STAGE: args.budget}) as client:
        try:
            results = run_eval(client, prompt, rows, abstracts, progress)
        except StopRun as exc:
            spent = log.spent_usd(EVAL_RUN_ID, STAGE)
            print(f"\nThe eval stopped after spending ${spent:.4f}: {exc}", file=sys.stderr)
            return 1

    cost = log.spent_usd(EVAL_RUN_ID, STAGE)
    scores = score(results)
    if args.report is not None:
        data = report(prompt, scores, results, cost)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        args.report.write_text(text, encoding="utf-8")
    print(summary(prompt.model, scores, cost))
    if args.write_baseline:
        write_baseline(args.baseline, baseline_data(prompt, scores, cost))
        print(f"Baseline written to {args.baseline}")
    if baseline is not None:
        problems = check(scores, baseline)
        if problems:
            print("\nRegression from the baseline:", file=sys.stderr)
            for problem in problems:
                print(f"- {problem}", file=sys.stderr)
            return 2
        print("No regression from the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
