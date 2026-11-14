"""Run the Writer: `python -m pipeline.writer`, or with `--article-id` (repeatable)
to write chosen articles again by hand. Exits 1 if the run failed or the Writer couldn't
run, such as on a configuration, database or lost-lock error. Exits 0 otherwise, including when
another run holds the lock or some articles failed (the run ends `partial` and sends its own
alert).
"""

import argparse
import logging
import sys
from collections.abc import Sequence

from sqlalchemy.exc import DBAPIError

from pipeline.db import worker_engine
from pipeline.models import load_prompt, stage_budget
from pipeline.models.calls import PostgresCallLog
from pipeline.models.openrouter import OpenRouterClient, OpenRouterSettings
from pipeline.notify import Alert, LoggingNotifier, Severity
from pipeline.runs import LockLost
from pipeline.writer.run import (
    DEFAULT_BUDGET_USD,
    PROMPT_NAME,
    STAGE,
    RunResult,
    WriterSettings,
    run_writer,
)


def _article_id(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(f"not an article ID: {value!r}")
    return number


def _parse_args(argv: list[str]) -> list[int] | None:
    parser = argparse.ArgumentParser(prog="python -m pipeline.writer", description=__doc__)
    parser.add_argument(
        "--article-id",
        type=_article_id,
        action="append",
        dest="article_ids",
        metavar="ID",
        help="an articles.id to write again; repeat for more",
    )
    args = parser.parse_args(argv)
    ids: list[int] | None = args.article_ids
    return sorted(set(ids)) if ids is not None else None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs every request at INFO, which adds nothing to the call log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    article_ids = _parse_args(sys.argv[1:] if argv is None else argv)
    notifier = LoggingNotifier()
    try:
        result = _run(notifier, article_ids)
    except LockLost:
        return 1  # Already alerted; the next run picks up its articles.
    except Exception as exc:
        # Configuration and database errors end up here. Database errors are kept short so
        # record content never reaches the alert.
        if isinstance(exc, DBAPIError):
            detail = f"Database error: {type(exc.orig).__name__}"
        else:
            detail = f"{type(exc).__name__}: {exc}"[:300]
        notifier.send(Alert(Severity.ERROR, "The Writer couldn't run", detail))
        return 1
    if result is None:
        return 0
    return 1 if result.status == "failed" else 0


def _run(notifier: LoggingNotifier, article_ids: Sequence[int] | None) -> RunResult | None:
    settings = WriterSettings.from_env()
    model_settings = OpenRouterSettings.from_env()
    budget = stage_budget(STAGE, DEFAULT_BUDGET_USD)
    prompt = load_prompt(PROMPT_NAME)
    engine = worker_engine()
    try:
        with OpenRouterClient(
            model_settings, log=PostgresCallLog(engine), budgets={STAGE: budget}
        ) as client:
            return run_writer(engine, client, prompt, notifier, settings, article_ids)
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
