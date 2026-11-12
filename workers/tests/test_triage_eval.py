"""The Triage eval scores scope decisions, counting failed calls against the paper."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from evals.triage.__main__ import summary
from evals.triage.run import PaperResult, approved_rows, report, run_eval, score
from pipeline.models import BudgetExceeded, CallRequest, ModelCallError
from pipeline.models.fake import FakeModelClient
from tests.prompt_files import write_prompt
from tests.triage_helpers import in_scope, out_of_scope, triage_prompt


def row(pmid: str, *topics: str, label: str = "approved") -> dict[str, Any]:
    return {
        "pmid": pmid,
        "title": f"Study {pmid}",
        "publication_types": ["Journal Article"],
        "label": label,
        "expected": {
            "in_scope": bool(topics),
            "topics": list(topics),
            "primary_topic": topics[0] if topics else None,
        },
    }


def result(pmid: str, expected: tuple[str, ...], **decision: Any) -> PaperResult:
    return PaperResult(pmid, bool(expected), expected, **decision)


def test_score_counts_misses_wrong_keeps_and_topics() -> None:
    results = [
        result("1", ("bone-health",), in_scope=True, primary_topic="bone-health"),
        result("2", ("bone-health", "longevity"), in_scope=True, primary_topic="longevity"),
        result("3", ("brain-health",), in_scope=True, primary_topic="longevity"),
        result("4", ("brain-health",), in_scope=False),
        result("5", (), in_scope=False),
        result("6", (), in_scope=True, primary_topic="longevity"),
    ]
    scores = score(results)
    assert (scores.papers, scores.in_scope, scores.out_of_scope) == (6, 4, 2)
    assert scores.missed_pmids == ("4",)
    assert scores.wrongly_kept_pmids == ("6",)
    assert scores.kept_in_scope == 0.75
    assert scores.dropped_out_of_scope == 0.5
    assert scores.accuracy == round(4 / 6, 4)
    assert scores.primary_topic_listed == round(2 / 3, 4)
    assert scores.primary_topic_exact == round(1 / 3, 4)
    assert scores.failed == 0


def test_failed_calls_count_against_the_paper() -> None:
    scores = score([result("1", ("bone-health",), error="boom"), result("2", (), error="boom")])
    assert scores.failed == 2
    assert scores.missed_pmids == ("1",)
    assert scores.wrongly_kept_pmids == ("2",)
    assert scores.accuracy == 0.0
    assert scores.primary_topic_listed is None


def test_only_approved_rows_count() -> None:
    rows = [row("1"), row("2", label="suggested")]
    assert [r["pmid"] for r in approved_rows(rows)] == ["1"]


def test_run_eval_sends_production_inputs_and_reads_replies(tmp_path: Path) -> None:
    prompt = triage_prompt(tmp_path)

    def respond(request: CallRequest) -> dict[str, Any] | Exception:
        if request.inputs["title"] == "Study 3":
            return ModelCallError("no provider")
        if request.inputs["title"] == "Study 1":
            return in_scope("muscle-and-strength", "bone-health")
        return out_of_scope()

    client = FakeModelClient(respond)
    rows = [row("1", "bone-health", "muscle-and-strength"), row("2"), row("3", "longevity")]
    abstracts = {"1": "First abstract.", "2": "Second.", "3": "Third."}
    seen: list[tuple[int, int]] = []
    results = run_eval(client, prompt, rows, abstracts, lambda d, t: seen.append((d, t)))

    assert client.requests[0].inputs == {
        "title": "Study 1",
        "abstract": "First abstract.",
        "publication_types": "Journal Article",
    }
    assert results[0].in_scope is True
    assert results[0].topics == ("muscle-and-strength", "bone-health")
    assert results[1].in_scope is False
    assert results[2].failed and results[2].error == "no provider"
    assert seen == [(1, 3), (2, 3), (3, 3)]
    scores = score(results)
    assert scores.missed_pmids == ("3",)
    assert scores.primary_topic_exact == 0.0
    assert scores.primary_topic_listed == 1.0


def test_an_unknown_topic_counts_as_a_failed_call(tmp_path: Path) -> None:
    prompt = triage_prompt(tmp_path)
    reply = {**in_scope(), "primary_topic": "none"}
    results = run_eval(FakeModelClient(lambda _: reply), prompt, [row("1")], {"1": "A."})
    assert results[0].failed
    assert results[0].error is not None and "primary topic" in results[0].error


def test_a_stopped_run_stops_the_eval(tmp_path: Path) -> None:
    prompt = triage_prompt(tmp_path)
    client = FakeModelClient(lambda _: BudgetExceeded("spent"))
    with pytest.raises(BudgetExceeded):
        run_eval(client, prompt, [row("1")], {"1": "A."})


def test_run_eval_needs_a_triage_prompt(tmp_path: Path) -> None:
    other = write_prompt(tmp_path, "grading/grade")
    with pytest.raises(ValueError, match="triage prompt"):
        run_eval(FakeModelClient(lambda _: {}), other, [], {})


def test_report_and_summary_hold_no_abstracts(tmp_path: Path) -> None:
    prompt = triage_prompt(tmp_path)
    results = run_eval(
        FakeModelClient(lambda _: out_of_scope()), prompt, [row("1")], {"1": "Secret abstract."}
    )
    scores = score(results)
    data = report(prompt, scores, results, Decimal("0.0012"))
    text = json.dumps(data)
    assert "Secret abstract." not in text
    assert data["scores"]["dropped_out_of_scope"] == 1.0
    assert data["cost_usd"] == "0.0012"
    lines = summary(prompt.model, scores, Decimal("0.0012"))
    assert "Out-of-scope papers dropped: 100.0%" in lines
    assert "In-scope papers kept: n/a" in lines
