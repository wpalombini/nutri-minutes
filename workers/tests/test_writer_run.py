"""Writer runs: selection, stale summaries, licences, storage, retries, failures, re-runs,
locking."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from pipeline.models import BudgetExceeded, ModelCallError
from pipeline.models.client import CallRequest
from pipeline.models.prompts import Prompt
from pipeline.notify import Severity
from pipeline.runs import agent_lock
from pipeline.writer.run import AGENT, WriterSettings, run_writer, select_articles
from tests.extractor_helpers import add_grade, insert_graded
from tests.fakes import FakeNotifier
from tests.triage_helpers import LoggedFakeClient
from tests.writer_helpers import (
    add_extraction,
    add_licence,
    insert_extracted,
    writer_prompt,
    written,
)

SETTINGS = WriterSettings(max_articles=100)


@pytest.fixture
def prompt(tmp_path: Path) -> Prompt:
    return writer_prompt(tmp_path)


def _summaries(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT a.title, m.* FROM summaries m JOIN articles a ON a.id = m.article_id "
                    "ORDER BY m.id"
                )
            )
        )


def _stages(engine: Engine) -> dict[str, tuple[str, str | None]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT a.title, s.status, s.error FROM article_stages s "
                "JOIN articles a ON a.id = s.article_id WHERE s.agent = 'writer'"
            )
        )
        return {row.title: (row.status, row.error) for row in rows}


def _by_title(replies: dict[str, dict[str, Any] | Exception]) -> Any:
    def respond(request: CallRequest) -> dict[str, Any] | Exception:
        return replies[request.inputs["title"]]

    return respond


def test_writes_and_stores(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        first = insert_extracted(conn, 1)
        insert_extracted(conn, 2, effect=False)
        insert_graded(conn, 3)  # graded, not extracted yet
        stale = insert_extracted(conn, 4)
        add_grade(conn, stale)  # re-graded since its extraction
    client = LoggedFakeClient(clean_engine, lambda _: written())
    notifier = FakeNotifier()
    result = run_writer(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "succeeded"
    assert [r.inputs["title"] for r in client.requests] == ["Study 1", "Study 2"]
    inputs = client.requests[0].inputs
    assert inputs["design"] == "randomised trial" and inputs["limit_count"] == "2 to 4"
    assert "Hazard ratio 0.80" in inputs["main_effect"]
    assert "No effect size" in client.requests[1].inputs["main_effect"]
    rows = _summaries(clean_engine)
    assert [r.title for r in rows] == ["Study 1", "Study 2"]
    one = rows[0]
    with clean_engine.connect() as conn:
        extraction_id = conn.execute(
            text("SELECT id FROM extractions WHERE article_id = :a"), {"a": first}
        ).scalar_one()
        call_article = conn.execute(
            text("SELECT article_id FROM model_calls WHERE id = :c"), {"c": one.model_call_id}
        ).scalar_one()
        limits = conn.execute(
            text(
                "SELECT position, statement FROM summary_limits WHERE summary_id = :s "
                "ORDER BY position"
            ),
            {"s": one.id},
        ).all()
    assert (one.extraction_id, one.source_basis, call_article) == (extraction_id, "abstract", first)
    assert one.headline == written()["headline"]
    assert one.body.count("\n\n") == 2
    assert one.absolute_sentence is not None
    assert [p for p, _ in limits] == [1, 2]
    assert set(_stages(clean_engine).values()) == {("done", None)}
    with clean_engine.connect() as conn:
        counts = conn.execute(
            text("SELECT counts FROM pipeline_runs WHERE id = :id"), {"id": result.run_id}
        ).scalar_one()
    assert counts == {"selected": 2, "written": 2, "failed": 0}
    assert notifier.alerts == []


def test_handled_articles_are_not_written_again(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_extracted(conn, 1)
    client = LoggedFakeClient(clean_engine, lambda _: written())
    run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert len(client.requests) == 1


def test_a_re_extraction_makes_summaries_and_failures_pending(
    clean_engine: Engine, prompt: Prompt
) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_extracted(conn, 1)
        failed = insert_extracted(conn, 2)
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": written(), "Study 2": ModelCallError("HTTP 503")})
    )
    run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert select_articles(clean_engine, 10) == []  # a failure isn't retried on its own
    with clean_engine.begin() as conn:
        new_extraction = add_extraction(conn, article_id)
        add_extraction(conn, failed)
    assert [a.id for a in select_articles(clean_engine, 10)] == [article_id, failed]

    run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    rows = _summaries(clean_engine)
    assert len(rows) == 2 and rows[-1].extraction_id == new_extraction
    assert select_articles(clean_engine, 10) == []  # failed again, with the new extraction


@pytest.mark.parametrize(
    ("licences", "may_reuse"),
    [
        ([], False),
        ([("cc-by", "europe_pmc")], True),
        ([("cc0", "europe_pmc")], True),
        ([("cc-by-nc", "europe_pmc")], False),
        ([("cc-by-nc", "europe_pmc"), ("cc-by", "europe_pmc")], True),  # current row wins
        ([("cc-by", "europe_pmc"), ("cc-by-nc", "pubmed")], False),  # every source must allow
    ],
)
def test_reuse_needs_every_source_s_current_licence(
    clean_engine: Engine, licences: list[tuple[str, str]], may_reuse: bool
) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_extracted(conn, 1)
        for code, source in licences:
            add_licence(conn, article_id, code, source)
    [article] = select_articles(clean_engine, 10)
    assert article.may_reuse_abstract is may_reuse


def test_failures_fail_only_that_article(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_extracted(conn, 1)
        insert_extracted(conn, 2)
        insert_extracted(conn, 3)
        insert_extracted(conn, 4, abstract="  ")
    client = LoggedFakeClient(
        clean_engine,
        _by_title(
            {
                "Study 1": ModelCallError("HTTP 503"),
                "Study 2": written(headline="An AI summary of vitamin D"),
                "Study 3": written(),
            }
        ),
    )
    notifier = FakeNotifier()
    result = run_writer(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "partial"
    stages = _stages(clean_engine)
    assert stages["Study 1"] == ("failed", "HTTP 503")
    assert stages["Study 2"][0] == "failed" and "artificial intelligence" in (
        stages["Study 2"][1] or ""
    )
    assert stages["Study 3"] == ("done", None)
    assert stages["Study 4"] == ("failed", "No abstract to write from")
    assert [r.inputs["title"] for r in client.requests].count("Study 2") == 3
    assert [a.severity for a in notifier.alerts] == [Severity.WARNING]


def test_each_call_gets_the_last_reply_s_reason(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_extracted(conn, 1)
    replies = iter(
        [
            written(headline="Vitamin D cut hip fractures by 20%"),
            written(limits=["Only older women."]),
            written(),
        ]
    )
    client = LoggedFakeClient(clean_engine, lambda _: next(replies))
    result = run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert result is not None and result.status == "succeeded"
    notes = [request.inputs["check_failure"] for request in client.requests]
    assert notes[0] == ""
    assert notes[1].startswith("<check_failure>") and "20 in the headline" in notes[1]
    assert "1 limits" in notes[2]
    with clean_engine.connect() as conn:
        last_call = conn.execute(text("SELECT max(id) FROM model_calls")).scalar_one()
    assert _summaries(clean_engine)[0].model_call_id == last_call


def test_an_extraction_replaced_mid_run_fails_the_article(
    clean_engine: Engine, prompt: Prompt
) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_extracted(conn, 1)

    def respond(request: CallRequest) -> dict[str, Any]:
        with clean_engine.begin() as conn:
            add_extraction(conn, article_id)
        return written()

    client = LoggedFakeClient(clean_engine, respond)
    result = run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert result is not None and result.status == "partial"
    status, error = _stages(clean_engine)["Study 1"]
    assert status == "failed" and "no longer the article's current extraction" in (error or "")
    assert _summaries(clean_engine) == []


def test_a_re_grade_mid_run_fails_the_article(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_extracted(conn, 1)

    def respond(request: CallRequest) -> dict[str, Any]:
        with clean_engine.begin() as conn:
            add_grade(conn, article_id)
        return written()

    client = LoggedFakeClient(clean_engine, respond)
    run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert _stages(clean_engine)["Study 1"][0] == "failed"
    assert _summaries(clean_engine) == []


def test_a_call_about_another_article_fails_it(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        first = insert_extracted(conn, 1)
        other = insert_extracted(conn, 2)
    client = LoggedFakeClient(clean_engine, lambda _: written())
    original = client.call

    def call(request: CallRequest) -> Any:
        return original(replace(request, article_id=other))

    client.call = call  # type: ignore[method-assign]
    run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS, [first])
    status, error = _stages(clean_engine)["Study 1"]
    assert status == "failed" and "isn't about article" in (error or "")


def test_stop_run_fails_the_run_and_leaves_the_rest(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_extracted(conn, 1)
        insert_extracted(conn, 2)
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": written(), "Study 2": BudgetExceeded("spent")})
    )
    notifier = FakeNotifier()
    result = run_writer(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "failed"
    assert _stages(clean_engine) == {"Study 1": ("done", None)}
    assert [a.severity for a in notifier.alerts] == [Severity.ERROR]


def test_max_articles_limits_a_run(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        for number in range(1, 4):
            insert_extracted(conn, number)
    client = LoggedFakeClient(clean_engine, lambda _: written())
    run_writer(clean_engine, client, prompt, FakeNotifier(), WriterSettings(max_articles=2))
    assert len(client.requests) == 2


def test_re_running_chosen_articles_adds_summaries(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        first = insert_extracted(conn, 1)
        unextracted = insert_graded(conn, 2)
    client = LoggedFakeClient(clean_engine, lambda _: written())
    run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS, [first, unextracted])

    assert len(client.requests) == 2
    assert len(_summaries(clean_engine)) == 2


def test_exits_when_another_run_holds_the_lock(clean_engine: Engine, prompt: Prompt) -> None:
    client = LoggedFakeClient(clean_engine, lambda _: written())
    with agent_lock(clean_engine, AGENT) as lock:
        assert lock is not None
        assert run_writer(clean_engine, client, prompt, FakeNotifier(), SETTINGS) is None


def test_needs_a_writer_prompt(clean_engine: Engine, tmp_path: Path) -> None:
    from tests.triage_helpers import triage_prompt

    client = LoggedFakeClient(clean_engine, lambda _: written())
    with pytest.raises(ValueError, match="writer prompt"):
        run_writer(clean_engine, client, triage_prompt(tmp_path), FakeNotifier(), SETTINGS)
