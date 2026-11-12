"""Grader runs: selection, rules, grades with reasons, failures, budgets, re-runs and locking."""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from pipeline.grader.run import AGENT, GraderSettings, run_grader, select_articles
from pipeline.models import BudgetExceeded, ModelCallError
from pipeline.models.client import CallRequest
from pipeline.models.prompts import Prompt
from pipeline.notify import Severity
from pipeline.runs import agent_lock
from tests.fakes import FakeNotifier
from tests.grader_helpers import graded, grader_prompt, insert_in_scope, move, not_gradable
from tests.triage_helpers import LoggedFakeClient

SETTINGS = GraderSettings(max_articles=100)


@pytest.fixture
def prompt(tmp_path: Path) -> Prompt:
    return grader_prompt(tmp_path)


def _grades(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT a.title, g.* FROM evidence_grades g JOIN articles a ON a.id = g.article_id "
                "ORDER BY g.id"
            )
        )
        return {row.title: row for row in rows}


def _reasons(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT grade_id, position, factor, direction, levels, reason "
                    "FROM evidence_grade_reasons ORDER BY grade_id, position"
                )
            )
        )


def _stages(engine: Engine) -> dict[str, tuple[str, str | None]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT a.title, s.status, s.error FROM article_stages s "
                "JOIN articles a ON a.id = s.article_id WHERE s.agent = 'grader'"
            )
        )
        return {row.title: (row.status, row.error) for row in rows}


def _counts(engine: Engine, run_id: int) -> dict[str, int]:
    with engine.connect() as conn:
        counts: dict[str, int] = conn.execute(
            text("SELECT counts FROM pipeline_runs WHERE id = :id"), {"id": run_id}
        ).scalar_one()
        return counts


def _by_title(replies: dict[str, dict[str, Any] | Exception]) -> Any:
    def respond(request: CallRequest) -> dict[str, Any] | Exception:
        return replies[request.inputs["title"]]

    return respond


def test_grades_and_stores(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_in_scope(conn, 1)
        insert_in_scope(conn, 2, publication_types=["Review"])
        insert_in_scope(conn, 3, publication_types=["Case Reports"])
        insert_in_scope(conn, 4, in_scope=False)
    funding = {
        "funder_type": "industry",
        "funder_sells_product": "yes",
        "sponsor_roles": ["analysis"],
        "funding_concern": "Funded by the supplement's maker, which ran the analysis.",
        "moves": [move("size", text="60 women."), move("duration", levels=0, text="A year.")],
    }
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": graded(**funding), "Study 2": not_gradable()})
    )
    notifier = FakeNotifier()
    result = run_grader(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "succeeded"
    assert [r.inputs["title"] for r in client.requests] == ["Study 1", "Study 2"]
    grades = _grades(clean_engine)
    assert set(grades) == {"Study 1", "Study 2", "Study 3"}
    first = grades["Study 1"]
    assert (first.design_category, first.starting_level, first.level) == ("randomised_trial", 4, 2)
    assert first.funding_lowered and first.sponsor_roles == ["analysis"]
    assert first.model_call_id is not None
    assert [(r.position, r.factor, r.levels) for r in _reasons(clean_engine)] == [
        (1, "size", 1),
        (2, "duration", 0),
        (3, "funding_and_conflicts", 1),
    ]
    assert (grades["Study 2"].decided_by, grades["Study 2"].not_gradable) == (
        "model",
        "narrative_review",
    )
    assert (grades["Study 3"].decided_by, grades["Study 3"].not_gradable) == ("rule", "case_report")
    assert set(_stages(clean_engine).values()) == {("done", None)}
    assert _counts(clean_engine, result.run_id) == {
        "selected": 3,
        "rule_not_gradable": 1,
        "not_gradable": 1,
        "graded": 1,
        "failed": 0,
    }
    assert notifier.alerts == []


def test_uses_the_latest_triage_decision(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_in_scope(conn, 1)
        run_id = conn.execute(text("SELECT max(id) FROM pipeline_runs")).scalar_one()
        conn.execute(
            text(
                "INSERT INTO triage_decisions (article_id, run_id, decided_by, rule, in_scope, "
                "reason) VALUES (:a, :r, 'rule', 'retracted', false, 'r')"
            ),
            {"a": article_id, "r": run_id},
        )
    assert select_articles(clean_engine, 10) == []


def test_grant_agencies_reach_the_prompt(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_in_scope(conn, 1)
        conn.execute(
            text("UPDATE articles SET source_record = CAST(:r AS jsonb) WHERE id = :id"),
            {"id": article_id, "r": '{"grantsList": {"grant": [{"agency": "Council A"}]}}'},
        )
    client = LoggedFakeClient(clean_engine, lambda _: graded())
    run_grader(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert client.requests[0].inputs["grant_agencies"] == "Council A"


def test_handled_articles_are_not_graded_again(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_in_scope(conn, 1)
    client = LoggedFakeClient(clean_engine, lambda _: graded())
    run_grader(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    run_grader(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert len(client.requests) == 1


def test_failures_fail_only_that_article(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_in_scope(conn, 1)
        insert_in_scope(conn, 2)
        insert_in_scope(conn, 3)
        insert_in_scope(conn, 4, abstract=None)
        insert_in_scope(conn, 5, abstract="  ")
        insert_in_scope(conn, 6)
    animal_rct = graded(design_category="animal")
    client = LoggedFakeClient(
        clean_engine,
        _by_title(
            {
                "Study 1": ModelCallError("HTTP 503"),
                "Study 2": animal_rct,
                "Study 3": graded(),
                "Study 6": graded(funding_source="grant_metadata"),
            }
        ),
    )
    notifier = FakeNotifier()
    result = run_grader(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "partial"
    stages = _stages(clean_engine)
    assert stages["Study 1"] == ("failed", "HTTP 503")
    assert stages["Study 2"][0] == "failed" and "study in people" in (stages["Study 2"][1] or "")
    assert stages["Study 3"] == ("done", None)
    assert stages["Study 4"] == ("failed", "No abstract to grade from")
    assert stages["Study 5"] == ("failed", "No abstract to grade from")
    assert stages["Study 6"][0] == "failed" and "grant list" in (stages["Study 6"][1] or "")
    assert [r.inputs["title"] for r in client.requests].count("Study 2") == 3
    assert [a.severity for a in notifier.alerts] == [Severity.WARNING]


def test_a_reply_that_makes_no_sense_is_asked_again(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_in_scope(conn, 1)
    replies = iter([graded(main_outcome=""), graded()])
    client = LoggedFakeClient(clean_engine, lambda _: next(replies))
    result = run_grader(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert result is not None and result.status == "succeeded"
    with clean_engine.connect() as conn:
        last_call = conn.execute(text("SELECT max(id) FROM model_calls")).scalar_one()
    assert _grades(clean_engine)["Study 1"].model_call_id == last_call


def test_stop_run_fails_the_run_and_leaves_the_rest(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_in_scope(conn, 1)
        insert_in_scope(conn, 2)
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": graded(), "Study 2": BudgetExceeded("spent")})
    )
    notifier = FakeNotifier()
    result = run_grader(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "failed"
    assert _stages(clean_engine) == {"Study 1": ("done", None)}
    assert [a.severity for a in notifier.alerts] == [Severity.ERROR]


def test_unexpected_errors_fail_only_that_article(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_in_scope(conn, 1)
        insert_in_scope(conn, 2)
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": RuntimeError("bug"), "Study 2": graded()})
    )
    result = run_grader(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert result is not None and result.status == "partial"
    assert _stages(clean_engine)["Study 1"][0] == "failed"
    assert _stages(clean_engine)["Study 2"] == ("done", None)


def test_max_articles_limits_a_run(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        for number in range(1, 4):
            insert_in_scope(conn, number)
    client = LoggedFakeClient(clean_engine, lambda _: graded())
    run_grader(clean_engine, client, prompt, FakeNotifier(), GraderSettings(max_articles=2))
    assert len(client.requests) == 2


def test_re_running_chosen_articles_adds_grades(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        first = insert_in_scope(conn, 1)
        out = insert_in_scope(conn, 2, in_scope=False)
    client = LoggedFakeClient(clean_engine, lambda _: graded())
    run_grader(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    run_grader(clean_engine, client, prompt, FakeNotifier(), SETTINGS, [first, out])

    assert len(client.requests) == 2
    with clean_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM evidence_grades")).scalar_one() == 2


def test_exits_when_another_run_holds_the_lock(clean_engine: Engine, prompt: Prompt) -> None:
    client = LoggedFakeClient(clean_engine, lambda _: graded())
    with agent_lock(clean_engine, AGENT) as lock:
        assert lock is not None
        assert run_grader(clean_engine, client, prompt, FakeNotifier(), SETTINGS) is None


def test_needs_a_grader_prompt(clean_engine: Engine, tmp_path: Path) -> None:
    from tests.triage_helpers import triage_prompt

    client = LoggedFakeClient(clean_engine, lambda _: graded())
    with pytest.raises(ValueError, match="grader prompt"):
        run_grader(clean_engine, client, triage_prompt(tmp_path), FakeNotifier(), SETTINGS)
