"""Run Scout: `python -m pipeline.scout`, or with `--window-start` and `--window-end` to
re-run a past window by hand. Exits 1 if a run failed or Scout couldn't run, such as on a
configuration, database or lost-lock error. Exits 0 otherwise, including when another run holds
the lock.
"""

import argparse
import logging
import sys
from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

from pipeline.db import database_url
from pipeline.europe_pmc import EuropePmcClient
from pipeline.notify import Alert, LoggingNotifier, Severity
from pipeline.runs import LockLost
from pipeline.scout.run import RunResult, Window, run_scout
from pipeline.scout.settings import ScoutSettings, client_settings_from_env


def _parse_args(argv: list[str], today: date) -> Window | None:
    parser = argparse.ArgumentParser(prog="python -m pipeline.scout", description=__doc__)
    parser.add_argument("--window-start", type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--window-end", type=date.fromisoformat, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    if (args.window_start is None) != (args.window_end is None):
        parser.error("--window-start and --window-end must be given together")
    if args.window_start is None:
        return None
    if args.window_end > today:
        parser.error("--window-end can't be in the future")
    if args.window_start > args.window_end:
        parser.error("--window-start can't be after --window-end")
    return Window(args.window_start, args.window_end)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs every request URL at INFO, which floods the log with the long query.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    today = datetime.now(UTC).date()
    window = _parse_args(sys.argv[1:] if argv is None else argv, today)
    notifier = LoggingNotifier()
    try:
        results = _run(notifier, today, window)
    except LockLost:
        return 1  # Already alerted; the run resumes next time.
    except Exception as exc:
        # Configuration, database and lost-lock errors end up here. Database errors are kept
        # short so record content never reaches the alert.
        if isinstance(exc, DBAPIError):
            detail = f"Database error: {type(exc.orig).__name__}"
        else:
            detail = f"{type(exc).__name__}: {exc}"[:300]
        notifier.send(Alert(Severity.ERROR, "Scout couldn't run", detail))
        return 1
    if results is None:
        return 0
    return 1 if any(result.status == "failed" for result in results) else 0


def _run(notifier: LoggingNotifier, today: date, window: Window | None) -> list[RunResult] | None:
    settings = ScoutSettings.from_env()
    client_settings = client_settings_from_env()
    engine = create_engine(
        database_url(),
        pool_pre_ping=True,
        # Keep record content out of error messages, logs and alerts.
        hide_parameters=True,
        # Notice a dead connection, such as the lock connection, instead of hanging.
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )
    try:
        with EuropePmcClient(client_settings) as client:
            return run_scout(engine, client, notifier, settings, today, window)
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
