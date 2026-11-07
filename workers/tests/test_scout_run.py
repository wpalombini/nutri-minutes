"""Scout runs: windows, paging, failed records, resuming, locking and alerts."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import Engine, text

from pipeline.europe_pmc import FIRST_CURSOR, EuropePmcError, SearchPage
from pipeline.notify import Alert, Severity
from pipeline.runs import agent_lock, start_run
from pipeline.scout.run import AGENT, Window, next_window, run_scout
from pipeline.scout.settings import ScoutSettings
from tests.records import record

TODAY = date(2026, 11, 7)
SETTINGS = ScoutSettings(search_terms="diet", initial_days=30, overlap_days=2, max_resumes=2)


@dataclass
class FakeClient:
    """Serves pages keyed by cursor, optionally failing on some cursors."""

    pages: dict[str, SearchPage]
    fail_on: set[str] = field(default_factory=set)
    queries: list[tuple[str, str]] = field(default_factory=list)

    def search(self, query: str, cursor: str = FIRST_CURSOR) -> SearchPage:
        self.queries.append((query, cursor))
        if cursor in self.fail_on:
            raise EuropePmcError("Search request failed after 5 attempts: HTTP 503")
        return self.pages[cursor]


@dataclass
class FakeNotifier:
    alerts: list[Alert] = field(default_factory=list)

    def send(self, alert: Alert) -> None:
        self.alerts.append(alert)


def _records(*ids: int) -> list[dict[str, Any]]:
    return [record(id=str(i), pmid=str(i), doi=f"10.1000/{i}", pmcid=f"PMC{i}") for i in ids]


def _two_pages(**kwargs: Any) -> FakeClient:
    return FakeClient(
        pages={
            FIRST_CURSOR: SearchPage(_records(1, 2), "c2", 3),
            "c2": SearchPage(_records(3), None, 3),
        },
        **kwargs,
    )


def _runs(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT id, status, parameters, checkpoint, counts, resume_count, error "
                    "FROM pipeline_runs ORDER BY id"
                )
            )
        )


def test_first_run_fetches_all_pages(clean_engine: Engine) -> None:
    client = _two_pages()
    notifier = FakeNotifier()
    results = run_scout(clean_engine, client, notifier, SETTINGS, TODAY)

    assert results is not None and [r.status for r in results] == ["succeeded"]
    [run] = _runs(clean_engine)
    assert run.parameters["window_start"] == "2026-10-08"
    assert run.parameters["window_end"] == "2026-11-07"
    assert "FIRST_IDATE:[2026-10-08 TO 2026-11-07]" in run.parameters["query"]
    assert run.counts["inserted"] == 3
    assert [cursor for _, cursor in client.queries] == [FIRST_CURSOR, "c2"]
    assert notifier.alerts == []


def test_next_window_starts_from_latest_completed_end(clean_engine: Engine) -> None:
    with clean_engine.begin() as conn:
        for end, status in (("2026-11-01", "succeeded"), ("2026-11-05", "failed")):
            run = start_run(conn, AGENT, {"window_end": end, "query": "x"})
            conn.execute(
                text("UPDATE pipeline_runs SET status = :s, finished_at = now() WHERE id = :id"),
                {"s": status, "id": run.id},
            )
    window = next_window(clean_engine, SETTINGS, TODAY)
    assert window == Window(date(2026, 10, 30), TODAY)


def test_failed_records_make_a_partial_run_and_alert(clean_engine: Engine) -> None:
    client = FakeClient(
        pages={FIRST_CURSOR: SearchPage([*_records(1), record(id="bad", title=None)], None, 2)}
    )
    notifier = FakeNotifier()
    results = run_scout(clean_engine, client, notifier, SETTINGS, TODAY)

    assert results is not None and results[0].status == "partial"
    [run] = _runs(clean_engine)
    assert (run.counts["inserted"], run.counts["failed"]) == (1, 1)
    with clean_engine.connect() as conn:
        error = conn.execute(text("SELECT source_record_id, error FROM pipeline_run_errors")).one()
    assert (error.source_record_id, error.error) == ("bad", "Record has no title")
    assert [a.severity for a in notifier.alerts] == [Severity.WARNING]


def test_source_failure_fails_the_run_and_alerts(clean_engine: Engine) -> None:
    notifier = FakeNotifier()
    results = run_scout(clean_engine, _two_pages(fail_on={"c2"}), notifier, SETTINGS, TODAY)

    assert results is not None and results[0].status == "failed"
    [run] = _runs(clean_engine)
    assert run.status == "failed"
    assert "HTTP 503" in run.error
    assert run.checkpoint == {"cursor": "c2"}
    assert run.counts["inserted"] == 2
    assert [a.severity for a in notifier.alerts] == [Severity.ERROR]


def test_dead_run_is_resumed_from_its_checkpoint(clean_engine: Engine) -> None:
    client = _two_pages()
    with clean_engine.begin() as conn:
        dead = start_run(
            conn, AGENT, {"query": "old", "window_start": "2026-11-01", "window_end": "2026-11-06"}
        )
        conn.execute(
            text('UPDATE pipeline_runs SET checkpoint = \'{"cursor": "c2"}\' WHERE id = :id'),
            {"id": dead.id},
        )

    results = run_scout(clean_engine, client, FakeNotifier(), SETTINGS, TODAY)

    assert results is not None and [r.run_id for r in results] == [dead.id, dead.id + 1]
    first, second = _runs(clean_engine)
    assert (first.status, first.resume_count) == ("succeeded", 1)
    assert client.queries[0] == ("old", "c2")
    assert second.status == "succeeded"


def test_dead_run_past_the_resume_cap_fails_and_alerts(clean_engine: Engine) -> None:
    with clean_engine.begin() as conn:
        dead = start_run(conn, AGENT, {"query": "old"})
        conn.execute(
            text("UPDATE pipeline_runs SET resume_count = 2 WHERE id = :id"), {"id": dead.id}
        )
    notifier = FakeNotifier()

    results = run_scout(clean_engine, _two_pages(), notifier, SETTINGS, TODAY)

    assert results is not None and [r.status for r in results] == ["failed", "succeeded"]
    first, _ = _runs(clean_engine)
    assert first.status == "failed"
    assert [a.severity for a in notifier.alerts] == [Severity.ERROR]


def test_manual_window(clean_engine: Engine) -> None:
    window = Window(date(2026, 9, 1), date(2026, 9, 3))
    run_scout(clean_engine, _two_pages(), FakeNotifier(), SETTINGS, TODAY, window)
    [run] = _runs(clean_engine)
    assert run.parameters["manual"] is True
    assert run.parameters["window_start"] == "2026-09-01"
    # A manual re-run of an old window doesn't move the next window back.
    assert next_window(clean_engine, SETTINGS, TODAY).start == date(2026, 9, 1)


def test_lock_held_elsewhere_skips(clean_engine: Engine) -> None:
    with agent_lock(clean_engine, AGENT) as lock:
        assert lock is not None
        client = _two_pages()
        assert run_scout(clean_engine, client, FakeNotifier(), SETTINGS, TODAY) is None
    assert client.queries == []
    assert _runs(clean_engine) == []


def test_rerunning_a_window_creates_no_duplicates(clean_engine: Engine) -> None:
    run_scout(clean_engine, _two_pages(), FakeNotifier(), SETTINGS, TODAY)
    run_scout(clean_engine, _two_pages(), FakeNotifier(), SETTINGS, TODAY)
    with clean_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM articles")).scalar_one() == 3
        assert conn.execute(text("SELECT count(*) FROM article_licences")).scalar_one() == 3
    second = _runs(clean_engine)[1]
    assert second.counts["unchanged"] == 3
