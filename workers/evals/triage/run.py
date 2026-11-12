"""Run Triage's prompt on the approved eval papers and score its scope decisions (ADR 0005).

Each paper goes to the model as production sends it, through the same client, prompt inputs and
reply checks. The papers all pass Triage's rules, so the eval scores the model's part alone.

Missing an in-scope paper is the costlier mistake, because nothing later finds it again, so
`kept_in_scope` (the share of in-scope papers kept) is the score that matters most. A call that
fails counts against the paper it was for: a missed paper if it was in scope, a wrong keep if not.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal
from typing import Any

from evals.abstracts import Row
from pipeline.models import CallRequest, ModelCallError, ModelClient, Prompt
from pipeline.triage.rules import TriageArticle
from pipeline.triage.run import MAX_ERROR_LENGTH, STAGE, ask_model, prompt_inputs

EVAL_RUN_ID = 0
"""Eval calls belong to no pipeline run. The in-memory call log keys the budget on this."""


@dataclass(frozen=True)
class PaperResult:
    pmid: str
    expected_in_scope: bool
    expected_topics: tuple[str, ...]
    in_scope: bool | None = None
    """None when the call failed."""
    relevance: int | None = None
    topics: tuple[str, ...] = ()
    primary_topic: str | None = None
    reason: str | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.in_scope is None

    @property
    def missed(self) -> bool:
        """An in-scope paper the model didn't keep, or whose call failed."""
        return self.expected_in_scope and self.in_scope is not True

    @property
    def wrongly_kept(self) -> bool:
        """An out-of-scope paper the model kept, or whose call failed."""
        return not self.expected_in_scope and self.in_scope is not False


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


@dataclass(frozen=True)
class Scores:
    papers: int
    in_scope: int
    out_of_scope: int
    failed: int
    missed: int
    wrongly_kept: int
    kept_in_scope: float | None
    """In-scope papers kept, as a share of all in-scope papers. The score that matters most."""
    dropped_out_of_scope: float | None
    """Out-of-scope papers dropped, as a share of all out-of-scope papers."""
    accuracy: float | None
    primary_topic_listed: float | None
    """Of the in-scope papers kept, the share whose primary topic is one of the expected topics."""
    primary_topic_exact: float | None
    """Of the in-scope papers kept, the share whose primary topic is the expected primary topic."""
    missed_pmids: tuple[str, ...] = field(default=())
    wrongly_kept_pmids: tuple[str, ...] = field(default=())


def score(results: Sequence[PaperResult]) -> Scores:
    in_scope = [r for r in results if r.expected_in_scope]
    out_of_scope = [r for r in results if not r.expected_in_scope]
    missed = [r for r in in_scope if r.missed]
    wrongly_kept = [r for r in out_of_scope if r.wrongly_kept]
    kept = [r for r in in_scope if not r.missed]
    listed = sum(r.primary_topic in r.expected_topics for r in kept)
    exact = sum(r.primary_topic == r.expected_topics[0] for r in kept)
    correct = len(results) - len(missed) - len(wrongly_kept)
    return Scores(
        papers=len(results),
        in_scope=len(in_scope),
        out_of_scope=len(out_of_scope),
        failed=sum(r.failed for r in results),
        missed=len(missed),
        wrongly_kept=len(wrongly_kept),
        kept_in_scope=_ratio(len(kept), len(in_scope)),
        dropped_out_of_scope=_ratio(len(out_of_scope) - len(wrongly_kept), len(out_of_scope)),
        accuracy=_ratio(correct, len(results)),
        primary_topic_listed=_ratio(listed, len(kept)),
        primary_topic_exact=_ratio(exact, len(kept)),
        missed_pmids=tuple(r.pmid for r in missed),
        wrongly_kept_pmids=tuple(r.pmid for r in wrongly_kept),
    )


def approved_rows(rows: Sequence[Row]) -> list[Row]:
    """Only approved labels count towards scores (`README.md`)."""
    return [row for row in rows if row["label"] == "approved"]


def article(row: Row, abstract: str) -> TriageArticle:
    """The row as Triage sees an article. The ID only labels the call."""
    return TriageArticle(
        id=0,
        title=row["title"],
        abstract=abstract,
        language="eng",
        publication_types=tuple(row["publication_types"]),
        retracted=False,
    )


def decide(client: ModelClient, prompt: Prompt, row: Row, abstract: str) -> PaperResult:
    """One paper's decision. `StopRun` propagates, because the eval can't finish without it."""
    expected = row["expected"]
    base = PaperResult(
        pmid=row["pmid"],
        expected_in_scope=expected["in_scope"],
        expected_topics=tuple(expected["topics"]),
    )
    try:
        request = CallRequest(EVAL_RUN_ID, prompt, prompt_inputs(article(row, abstract)))
        decision, _ = ask_model(client, request)
    except ModelCallError as exc:
        return replace(base, error=str(exc)[:MAX_ERROR_LENGTH] or type(exc).__name__)
    return replace(
        base,
        in_scope=decision.in_scope,
        relevance=decision.relevance,
        topics=decision.topics,
        primary_topic=decision.primary_topic,
        reason=decision.reason,
    )


def run_eval(
    client: ModelClient,
    prompt: Prompt,
    rows: Sequence[Row],
    abstracts: Mapping[str, str],
    progress: Callable[[int, int], None] | None = None,
) -> list[PaperResult]:
    """Every row's decision, in dataset order."""
    if prompt.stage != STAGE:
        raise ValueError(f"The Triage eval needs a {STAGE} prompt, not {prompt.name}")
    results = []
    for number, row in enumerate(rows, start=1):
        results.append(decide(client, prompt, row, abstracts[row["pmid"]]))
        if progress is not None:
            progress(number, len(rows))
    return results


def report(
    prompt: Prompt, scores: Scores, results: Sequence[PaperResult], cost_usd: Decimal
) -> dict[str, Any]:
    """The run as JSON. It leaves out abstracts, which may not be reusable, but keeps the model's
    reasons, which may quote them: keep reports outside the repo."""
    return {
        "prompt": prompt.name,
        "prompt_version": prompt.version,
        "model": prompt.model,
        "cost_usd": str(cost_usd),
        "scores": asdict(scores),
        "papers": [asdict(result) for result in results],
    }
