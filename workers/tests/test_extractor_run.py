"""Extractor runs: selection, stale extractions, storage, retries, failures, re-runs, locking."""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from pipeline.extractor.run import AGENT, ExtractorSettings, run_extractor, select_articles
from pipeline.models import BudgetExceeded, ModelCallError
from pipeline.models.client import CallRequest
from pipeline.models.prompts import Prompt
from pipeline.notify import Severity
from pipeline.runs import agent_lock
from tests.extractor_helpers import (
    NO_EFFECT,
    add_grade,
    extracted,
    extractor_prompt,
    fact,
    insert_graded,
)
from tests.fakes import FakeNotifier
from tests.grader_helpers import insert_in_scope
from tests.triage_helpers import LoggedFakeClient

SETTINGS = ExtractorSettings(max_articles=100)


@pytest.fixture
def prompt(tmp_path: Path) -> Prompt:
    return extractor_prompt(tmp_path)


def _extractions(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT a.title, x.* FROM extractions x JOIN articles a ON a.id = x.article_id "
                    "ORDER BY x.id"
                )
            )
        )


def _stages(engine: Engine) -> dict[str, tuple[str, str | None]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT a.title, s.status, s.error FROM article_stages s "
                "JOIN articles a ON a.id = s.article_id WHERE s.agent = 'extractor'"
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


def test_extracts_and_stores(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        first = insert_graded(conn, 1)
        insert_graded(conn, 2)
        insert_graded(conn, 3, gradable=False)
        insert_in_scope(conn, 4)  # not graded yet
        out = insert_graded(conn, 5)
        run_id = conn.execute(text("SELECT max(id) FROM pipeline_runs")).scalar_one()
        conn.execute(
            text(
                "INSERT INTO triage_decisions (article_id, run_id, decided_by, rule, in_scope, "
                "reason) VALUES (:a, :r, 'rule', 'retracted', false, 'r')"
            ),
            {"a": out, "r": run_id},
        )
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": extracted(), "Study 2": extracted(**NO_EFFECT)})
    )
    notifier = FakeNotifier()
    result = run_extractor(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "succeeded"
    assert [r.inputs["title"] for r in client.requests] == ["Study 1", "Study 2"]
    inputs = client.requests[0].inputs
    assert (inputs["design"], inputs["main_outcome"], inputs["participants"]) == (
        "randomised trial",
        "hip fracture",
        "1200",
    )
    rows = _extractions(clean_engine)
    assert [r.title for r in rows] == ["Study 1", "Study 2"]
    one = rows[0]
    with clean_engine.connect() as conn:
        grade_id = conn.execute(
            text("SELECT id FROM evidence_grades WHERE article_id = :a"), {"a": first}
        ).scalar_one()
        facts = list(
            conn.execute(
                text(
                    "SELECT position, kind FROM extraction_facts WHERE extraction_id = :x "
                    "ORDER BY position"
                ),
                {"x": one.id},
            )
        )
    assert (one.grade_id, one.source_basis, one.measure) == (grade_id, "abstract", "hazard_ratio")
    assert (str(one.estimate), str(one.ci_lower), str(one.ci_level)) == ("0.80", "0.65", "95")
    assert one.model_call_id is not None
    assert [(f.position, f.kind) for f in facts] == [
        (1, "outcome"),
        (2, "result"),
        (3, "absolute"),
        (4, "limitation"),
    ]
    assert rows[1].measure is None and rows[1].estimate is None
    assert set(_stages(clean_engine).values()) == {("done", None)}
    assert _counts(clean_engine, result.run_id) == {
        "selected": 2,
        "with_main_effect": 1,
        "without_main_effect": 1,
        "failed": 0,
    }
    assert notifier.alerts == []


def test_handled_articles_are_not_extracted_again(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_graded(conn, 1)
    client = LoggedFakeClient(clean_engine, lambda _: extracted())
    run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert len(client.requests) == 1


def test_a_re_grade_makes_extractions_and_failures_pending(
    clean_engine: Engine, prompt: Prompt
) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_graded(conn, 1)
        failed = insert_graded(conn, 2)
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": extracted(), "Study 2": ModelCallError("HTTP 503")})
    )
    run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    assert select_articles(clean_engine, 10) == []  # a failure isn't retried on its own
    with clean_engine.begin() as conn:
        new_grade = add_grade(conn, article_id)
        add_grade(conn, failed)
    assert [a.id for a in select_articles(clean_engine, 10)] == [article_id, failed]

    run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    rows = _extractions(clean_engine)
    assert [r.grade_id for r in rows][-1] == new_grade and len(rows) == 2
    assert select_articles(clean_engine, 10) == []  # failed again, with the new grade


def test_a_re_grade_to_not_gradable_is_skipped(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_graded(conn, 1)
        add_grade(conn, article_id, gradable=False)
    assert select_articles(clean_engine, 10) == []
    assert select_articles(clean_engine, 10, [article_id]) == []


def test_failures_fail_only_that_article(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_graded(conn, 1)
        insert_graded(conn, 2)
        insert_graded(conn, 3)
        insert_graded(conn, 4, abstract="  ")
    client = LoggedFakeClient(
        clean_engine,
        _by_title(
            {
                "Study 1": ModelCallError("HTTP 503"),
                "Study 2": extracted(population_quote="Not in the abstract"),
                "Study 3": extracted(),
            }
        ),
    )
    notifier = FakeNotifier()
    result = run_extractor(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "partial"
    stages = _stages(clean_engine)
    assert stages["Study 1"] == ("failed", "HTTP 503")
    assert stages["Study 2"] == ("failed", "The population quote isn't in the abstract")
    assert stages["Study 3"] == ("done", None)
    assert stages["Study 4"] == ("failed", "No abstract to extract from")
    assert [r.inputs["title"] for r in client.requests].count("Study 2") == 3
    assert [a.severity for a in notifier.alerts] == [Severity.WARNING]


def test_a_reply_that_fails_the_checks_is_asked_again(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_graded(conn, 1)
    replies = iter([extracted(estimate="0.8"), extracted()])
    client = LoggedFakeClient(clean_engine, lambda _: next(replies))
    result = run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert result is not None and result.status == "succeeded"
    with clean_engine.connect() as conn:
        last_call = conn.execute(text("SELECT max(id) FROM model_calls")).scalar_one()
    assert _extractions(clean_engine)[0].model_call_id == last_call
    first, second = (request.inputs["check_failure"] for request in client.requests)
    assert first == ""
    assert second.startswith("<check_failure>") and "0.8" in second


def test_the_last_call_drops_bad_facts(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_graded(conn, 1)
    bad = fact("result", "Bone density rose by 2.4%.", "Bone density rose by 1.2% (p = 0.03).")
    client = LoggedFakeClient(clean_engine, lambda _: extracted(facts=[bad, *extracted()["facts"]]))
    result = run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert result is not None and result.status == "succeeded"
    assert len(client.requests) == 3
    with clean_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT position, fact FROM extraction_facts ORDER BY position")
        ).all()
    assert [position for position, _ in stored] == [1, 2, 3, 4]
    assert "Bone density rose by 2.4%." not in [fact for _, fact in stored]


def test_a_grade_replaced_mid_run_fails_the_article(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        article_id = insert_graded(conn, 1)

    def respond(request: CallRequest) -> dict[str, Any]:
        with clean_engine.begin() as conn:
            add_grade(conn, article_id)
        return extracted()

    client = LoggedFakeClient(clean_engine, respond)
    result = run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS)

    assert result is not None and result.status == "partial"
    status, error = _stages(clean_engine)["Study 1"]
    assert status == "failed" and "no longer the article's current grade" in (error or "")
    assert _extractions(clean_engine) == []


def test_stop_run_fails_the_run_and_leaves_the_rest(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        insert_graded(conn, 1)
        insert_graded(conn, 2)
    client = LoggedFakeClient(
        clean_engine, _by_title({"Study 1": extracted(), "Study 2": BudgetExceeded("spent")})
    )
    notifier = FakeNotifier()
    result = run_extractor(clean_engine, client, prompt, notifier, SETTINGS)

    assert result is not None and result.status == "failed"
    assert _stages(clean_engine) == {"Study 1": ("done", None)}
    assert [a.severity for a in notifier.alerts] == [Severity.ERROR]


def test_max_articles_limits_a_run(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        for number in range(1, 4):
            insert_graded(conn, number)
    client = LoggedFakeClient(clean_engine, lambda _: extracted())
    run_extractor(clean_engine, client, prompt, FakeNotifier(), ExtractorSettings(max_articles=2))
    assert len(client.requests) == 2


def test_re_running_chosen_articles_adds_extractions(clean_engine: Engine, prompt: Prompt) -> None:
    with clean_engine.begin() as conn:
        first = insert_graded(conn, 1)
        ungraded = insert_in_scope(conn, 2)
    client = LoggedFakeClient(clean_engine, lambda _: extracted())
    run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS)
    run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS, [first, ungraded])

    assert len(client.requests) == 2
    assert len(_extractions(clean_engine)) == 2


def test_exits_when_another_run_holds_the_lock(clean_engine: Engine, prompt: Prompt) -> None:
    client = LoggedFakeClient(clean_engine, lambda _: extracted())
    with agent_lock(clean_engine, AGENT) as lock:
        assert lock is not None
        assert run_extractor(clean_engine, client, prompt, FakeNotifier(), SETTINGS) is None


def test_needs_an_extractor_prompt(clean_engine: Engine, tmp_path: Path) -> None:
    from tests.triage_helpers import triage_prompt

    client = LoggedFakeClient(clean_engine, lambda _: extracted())
    with pytest.raises(ValueError, match="extractor prompt"):
        run_extractor(clean_engine, client, triage_prompt(tmp_path), FakeNotifier(), SETTINGS)
