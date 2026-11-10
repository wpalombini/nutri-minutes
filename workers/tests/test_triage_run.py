"""Triage runs: rules, model decisions, failures, budgets, re-runs and locking."""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from pipeline.models import BudgetExceeded, ModelCallError
from pipeline.models.client import CallRequest
from pipeline.models.prompts import Prompt
from pipeline.notify import Severity
from pipeline.runs import agent_lock, start_run
from pipeline.triage.run import AGENT, TriageSettings, run_triage, select_articles
from tests.test_scout_run import FakeNotifier
from tests.triage_helpers import LoggedFakeClient, in_scope, insert_article, out_of_scope

SETTINGS = TriageSettings(max_articles=100)


@pytest.fixture
def prompt(tmp_path: Path) -> Prompt:
    from tests.triage_helpers import triage_prompt

    return triage_prompt(tmp_path)


def _decisions(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT a.title, d.decided_by, d.rule, d.in_scope, d.relevance, d.topics, "
                    "d.primary_topic, d.model_call_id, d.run_id FROM triage_decisions d "
                    "JOIN articles a ON a.id = d.article_id ORDER BY d.id"
                )
            )
        )


def _stages(engine: Engine) -> dict[str, tuple[str, str | None]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT a.title, s.status, s.error FROM article_stages s "
                "JOIN articles a ON a.id = s.article_id WHERE s.agent = 'triage'"
            )
        )
        return {row.title: (row.status, row.error) for row in rows}


def _run_row(engine: Engine, run_id: int) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT status, counts, error, parameters FROM pipeline_runs WHERE id = :id"),
            {"id": run_id},
        ).one()


def _by_title(replies: dict[str, dict[str, Any] | Exception]) -> Any:
    def respond(request: CallRequest) -> dict[str, Any] | Exception:
        return replies[request.inputs["title"]]

    return respond


def test_rules_and_model_decide_and_store(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_article(conn, 1)
        insert_article(conn, 2)
        insert_article(conn, 3, abstract=None)
        insert_article(conn, 4, publication_types=["Editorial"])
    client = LoggedFakeClient(
        clean_engine,
        _by_title(
            {
                "Study 1": in_scope("bone-health", "falls-and-independence"),
                "Study 2": out_of_scope(),
            }
        ),
    )
    notifier = FakeNotifier()
    result = run_triage(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "succeeded"
    assert [r.inputs["title"] for r in client.requests] == ["Study 1", "Study 2"]
    rows = {row.title: row for row in _decisions(clean_engine)}
    assert rows["Study 1"].in_scope and rows["Study 1"].relevance == 4
    assert rows["Study 1"].topics == ["bone-health", "falls-and-independence"]
    assert rows["Study 1"].primary_topic == "bone-health"
    assert rows["Study 1"].model_call_id is not None
    assert not rows["Study 2"].in_scope and rows["Study 2"].topics == []
    assert (rows["Study 3"].decided_by, rows["Study 3"].rule) == ("rule", "no_abstract")
    assert rows["Study 4"].rule == "not_research"
    assert set(_stages(clean_engine).values()) == {("done", None)}
    run = _run_row(clean_engine, result.run_id)
    assert run.counts == {
        "selected": 4,
        "rule_out": 2,
        "in_scope": 1,
        "out_of_scope": 1,
        "failed": 0,
    }
    assert run.parameters["prompt_version"] == prompt.version
    assert notifier.alerts == []


def test_handled_articles_are_not_decided_again(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_article(conn, 1)
    client = LoggedFakeClient(clean_engine, lambda _: in_scope())
    run_triage(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    second = run_triage(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert second is not None and second.status == "succeeded"
    assert len(client.requests) == 1
    assert len(_decisions(clean_engine)) == 1


def test_retracted_articles_are_dropped(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        first = insert_article(conn, 1)
        second = insert_article(conn, 2)
        notice = insert_article(conn, 3, publication_types=["Retraction of Publication"])
        insert_article(conn, 4, publication_types=["Journal Article", "Retracted Publication"])
        conn.execute(
            text(
                "INSERT INTO article_relations (article_id, relation_type, raw_type, "
                "target_source, target_id) VALUES (:id, 'retraction_in', 'Retraction in', "
                "'MED', '999')"
            ),
            {"id": first},
        )
        conn.execute(
            text(
                "INSERT INTO article_relations (article_id, relation_type, raw_type, "
                "target_source, target_id, related_article_id) VALUES (:notice, "
                "'retraction_of', 'Retraction of', 'MED', '2', :id)"
            ),
            {"notice": notice, "id": second},
        )
    client = LoggedFakeClient(clean_engine, lambda _: in_scope())
    run_triage(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    rules = {row.title: row.rule for row in _decisions(clean_engine)}
    assert rules == {
        "Study 1": "retracted",
        "Study 2": "retracted",
        "Study 3": "not_research",
        "Study 4": "retracted",
    }
    assert client.requests == []


def test_a_failed_call_fails_only_that_article(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_article(conn, 1)
        insert_article(conn, 2)
        insert_article(conn, 3)
    bad_reply = {**in_scope(), "primary_topic": "none"}
    client = LoggedFakeClient(
        clean_engine,
        _by_title(
            {"Study 1": ModelCallError("HTTP 503"), "Study 2": bad_reply, "Study 3": in_scope()}
        ),
    )
    notifier = FakeNotifier()
    result = run_triage(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "partial"
    stages = _stages(clean_engine)
    assert stages["Study 1"] == ("failed", "HTTP 503")
    assert stages["Study 2"][0] == "failed" and "primary topic" in (stages["Study 2"][1] or "")
    assert stages["Study 3"] == ("done", None)
    assert [a.severity for a in notifier.alerts] == [Severity.WARNING]

    # Failed articles are skipped by later runs.
    again = run_triage(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert again is not None and _run_row(clean_engine, again.run_id).counts["selected"] == 0


def test_every_article_failing_is_an_error_alert(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_article(conn, 1)
    notifier = FakeNotifier()
    client = LoggedFakeClient(clean_engine, lambda _: ModelCallError("down"))
    run_triage(clean_engine, client, prompt, notifier, SETTINGS)
    assert [a.severity for a in notifier.alerts] == [Severity.ERROR]


def test_stop_run_fails_the_run_and_leaves_the_rest(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_article(conn, 1)
        insert_article(conn, 2)
        insert_article(conn, 3)
    client = LoggedFakeClient(
        clean_engine,
        _by_title({"Study 1": in_scope(), "Study 2": BudgetExceeded("spent")}),
    )
    notifier = FakeNotifier()
    result = run_triage(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "failed"
    run = _run_row(clean_engine, result.run_id)
    assert run.status == "failed" and "BudgetExceeded: spent" in run.error
    assert _stages(clean_engine) == {"Study 1": ("done", None)}
    assert [a.severity for a in notifier.alerts] == [Severity.ERROR]

    # The next run picks up where it stopped.
    client = LoggedFakeClient(clean_engine, lambda _: out_of_scope())
    run_triage(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert [r.inputs["title"] for r in client.requests] == ["Study 2", "Study 3"]


def test_unexpected_errors_fail_only_that_article(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_article(conn, 1)
        insert_article(conn, 2)
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": RuntimeError("bug"), "Study 2": in_scope()})
    )
    result = run_triage(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert result is not None and result.status == "partial"
    assert _stages(clean_engine) == {
        "Study 1": ("failed", "RuntimeError: bug"),
        "Study 2": ("done", None),
    }


def test_max_articles_limits_a_run(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        for number in (1, 2, 3):
            insert_article(conn, number)
    client = LoggedFakeClient(clean_engine, lambda _: in_scope())
    run_triage(clean_engine, client, prompt, FakeNotifier(), TriageSettings(max_articles=2))
    assert [r.inputs["title"] for r in client.requests] == ["Study 1", "Study 2"]


def test_re_running_chosen_articles_adds_decisions(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        first = insert_article(conn, 1)
        insert_article(conn, 2)
    failing = LoggedFakeClient(clean_engine, lambda _: ModelCallError("down"))
    run_triage(clean_engine, failing, prompt, FakeNotifier(), SETTINGS)

    client = LoggedFakeClient(clean_engine, lambda _: in_scope())
    result = run_triage(clean_engine, client, prompt, FakeNotifier(), SETTINGS, [first])

    assert result is not None and result.status == "succeeded"
    assert [r.article_id for r in client.requests] == [first]
    stages = _stages(clean_engine)
    assert stages["Study 1"] == ("done", None)
    assert stages["Study 2"][0] == "failed"
    assert _run_row(clean_engine, result.run_id).parameters["article_ids"] == [first]


def test_dead_run_is_marked_failed(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        dead = start_run(conn, AGENT, {})
        insert_article(conn, 1)
    notifier = FakeNotifier()
    client = LoggedFakeClient(clean_engine, lambda _: in_scope())
    result = run_triage(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "succeeded"
    assert _run_row(clean_engine, dead.id).status == "failed"
    assert [a.severity for a in notifier.alerts] == [Severity.WARNING]


def test_exits_when_another_run_holds_the_lock(clean_engine: Engine, prompt: Prompt) -> None:
    client = LoggedFakeClient(clean_engine, lambda _: in_scope())
    with agent_lock(clean_engine, AGENT) as lock:
        assert lock is not None
        assert run_triage(clean_engine, client, prompt, FakeNotifier(), SETTINGS) is None


def test_needs_a_triage_prompt(clean_engine: Engine, tmp_path: Path) -> None:
    from tests.prompt_files import write_prompt

    other = write_prompt(tmp_path, "grader/grade")
    client = LoggedFakeClient(clean_engine, lambda _: in_scope())
    with pytest.raises(ValueError, match="triage"):
        run_triage(clean_engine, client, other, FakeNotifier(), SETTINGS)


def test_select_articles_skips_handled_ones(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_article(conn, 1, publication_types=["Editorial"])
        insert_article(conn, 2)
    client = LoggedFakeClient(clean_engine, lambda _: in_scope())
    run_triage(clean_engine, client, prompt, FakeNotifier(), TriageSettings(max_articles=1))
    assert [a.title for a in select_articles(clean_engine, 10)] == ["Study 2"]
