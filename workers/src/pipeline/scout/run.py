"""Scout runs: fetch new papers from Europe PMC and store them, page by page.

Run rules are in docs/database.md (`pipeline_runs`) and the steps in docs/agents.md (Scout).
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from pipeline.europe_pmc import FIRST_CURSOR, SearchPage, build_query
from pipeline.notify import Alert, Notifier, Severity
from pipeline.runs import (
    AgentLock,
    LockLost,
    Run,
    agent_lock,
    find_running,
    finish_run,
    mark_resumed,
    record_error,
    save_progress,
    start_run,
)
from pipeline.scout.normalise import SOURCE, RecordError, normalise, record_id
from pipeline.scout.settings import ScoutSettings
from pipeline.scout.store import store

logger = logging.getLogger(__name__)

AGENT = "scout"
COUNT_KEYS = ("fetched", "inserted", "updated", "unchanged", "failed")


class SearchClient(Protocol):
    def search(self, query: str, cursor: str = FIRST_CURSOR) -> SearchPage: ...


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("A window can't start after it ends")


@dataclass(frozen=True)
class RunResult:
    run_id: int
    status: str


def next_window(engine: Engine, settings: ScoutSettings, today: date) -> Window:
    """Start at the latest completed window's end, less the overlap, and end today."""
    with engine.connect() as conn:
        latest = conn.execute(
            text(
                "SELECT max((parameters->>'window_end')::date) FROM pipeline_runs "
                "WHERE agent = :agent AND status IN ('succeeded', 'partial')"
            ),
            {"agent": AGENT},
        ).scalar()
    if latest is None:
        start = today - timedelta(days=settings.initial_days)
    else:
        start = min(latest - timedelta(days=settings.overlap_days), today)
    return Window(start=start, end=today)


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


def _execute(
    engine: Engine, lock: AgentLock, client: SearchClient, notifier: Notifier, run: Run
) -> str:
    for key in COUNT_KEYS:
        run.counts.setdefault(key, 0)
    query = str(run.parameters["query"])
    cursor = str((run.checkpoint or {}).get("cursor", FIRST_CURSOR))
    try:
        while True:
            page = client.search(query, cursor)
            with engine.begin() as conn:
                for record in page.records:
                    run.counts["fetched"] += 1
                    savepoint = conn.begin_nested()
                    try:
                        outcome = store(conn, normalise(record))
                    except (RecordError, DBAPIError) as exc:
                        savepoint.rollback()
                        if isinstance(exc, DBAPIError):
                            message = f"Database rejected the record: {type(exc.orig).__name__}"
                        else:
                            message = str(exc)
                        record_error(
                            conn,
                            run,
                            source=SOURCE,
                            source_record_id=record_id(record),
                            error=message,
                            raw_record=record,
                        )
                        run.counts["failed"] += 1
                    else:
                        savepoint.commit()
                        run.counts[outcome.value] += 1
                run.checkpoint = {"cursor": page.next_cursor or cursor}
                save_progress(conn, run)
                lock.check()
            if page.next_cursor is None or not page.records:
                break
            cursor = page.next_cursor
    except LockLost:
        raise
    except Exception as exc:
        logger.exception("Scout run %d failed", run.id)
        with engine.begin() as conn:
            finish_run(conn, run, "failed", _error_text(exc))
        notifier.send(Alert(Severity.ERROR, f"Scout run {run.id} failed", _error_text(exc)))
        return "failed"

    status = "partial" if run.counts["failed"] else "succeeded"
    with engine.begin() as conn:
        finish_run(conn, run, status)
    logger.info("Scout run %d %s: %s", run.id, status, run.counts)
    if status == "partial":
        window = f"{run.parameters['window_start']} to {run.parameters['window_end']}"
        notifier.send(
            Alert(
                Severity.WARNING,
                f"Scout run {run.id} finished with failed records",
                f"{run.counts['failed']} of {run.counts['fetched']} records failed for "
                f"{window}. They're in pipeline_run_errors. Fix the cause, then re-run "
                "that window.",
            )
        )
    return status


def run_scout(
    engine: Engine,
    client: SearchClient,
    notifier: Notifier,
    settings: ScoutSettings,
    today: date,
    window: Window | None = None,
) -> list[RunResult] | None:
    """Run Scout once. Returns None if another worker holds the lock.

    A dead run is dealt with first: resumed, or marked failed after too many resumes. Then a
    new run covers `window`, or the next scheduled window if none is given.
    """
    with agent_lock(engine, AGENT) as lock:
        if lock is None:
            logger.info("Another Scout run holds the lock, so this one is exiting")
            return None
        results: list[RunResult] = []

        with engine.begin() as conn:
            dead = find_running(conn, AGENT)
            resume = dead is not None and dead.resume_count < settings.max_resumes
            if dead is not None and resume:
                mark_resumed(conn, dead)
            elif dead is not None:
                finish_run(conn, dead, "failed", f"Resumed {dead.resume_count} times")
        if dead is not None and resume:
            logger.info("Resuming dead Scout run %d", dead.id)
            results.append(RunResult(dead.id, _execute(engine, lock, client, notifier, dead)))
        elif dead is not None:
            notifier.send(
                Alert(
                    Severity.ERROR,
                    f"Scout run {dead.id} failed",
                    f"It crashed and had already been resumed {dead.resume_count} times.",
                )
            )
            results.append(RunResult(dead.id, "failed"))

        chosen = window or next_window(engine, settings, today)
        parameters = {
            "search_terms": settings.search_terms,
            "query": build_query(settings.search_terms, chosen.start, chosen.end),
            "window_start": chosen.start.isoformat(),
            "window_end": chosen.end.isoformat(),
            "manual": window is not None,
        }
        with engine.begin() as conn:
            run = start_run(conn, AGENT, parameters)
        logger.info("Starting Scout run %d for %s to %s", run.id, chosen.start, chosen.end)
        results.append(RunResult(run.id, _execute(engine, lock, client, notifier, run)))
        return results
