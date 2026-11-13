"""Run the Evidence Grader on the approved eval papers and score its grades (ADR 0005).

Each paper goes through production's path: the rules first (`pipeline.grader.rules`), then the
model through the same client, prompt inputs and reply checks, then the code that turns the
reply into a grade. A rule's decision costs nothing and is scored like the model's.

Scores (`README.md`):
- **Design label:** the design category, or the reason a paper isn't gradable, matches the label.
  Calling a study in people an animal or lab study, or the reverse, is the worst error
  (`mixups`).
- **Level:** exact agreement and agreement within one level, on papers both the label and the
  Grader call gradable.

A failed call counts as a wrong design label and drops out of the level scores, so the baseline
check also caps failed calls.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal
from typing import Any

from evals.abstracts import Row
from pipeline.grader.grading import FUNDING, Grade, declared_conflicts
from pipeline.grader.rules import GraderArticle, apply_rules
from pipeline.grader.run import MAX_ERROR_LENGTH, STAGE, ask_model, prompt_inputs
from pipeline.models import CallRequest, ModelCallError, ModelClient, Prompt

EVAL_RUN_ID = 0
"""Eval calls belong to no pipeline run. The in-memory call log keys the budget on this."""

NOT_IN_PEOPLE = ("animal", "lab")


def design_label(gradable: bool, design: str | None, not_gradable: str | None) -> str | None:
    """The design category, or the reason the paper isn't gradable."""
    return design if gradable else not_gradable


def in_people(design: str | None, includes: str | None) -> bool | None:
    """Whether a gradable design studies people. None when there is no design."""
    if design is None:
        return None
    return design not in NOT_IN_PEOPLE and includes != "animal_or_lab"


@dataclass(frozen=True)
class PaperResult:
    pmid: str
    expected_label: str
    expected_in_people: bool | None
    expected_level: int | None
    label: str | None = None
    """None when the call failed."""
    decided_by: str | None = None
    """`rule` or `model`."""
    in_people: bool | None = None
    level: int | None = None
    funding_concern: str | None = None
    funding_lowered: bool | None = None
    reason: str | None = None
    starting_level: int | None = None
    moves: tuple[str, ...] = ()
    """Each move the grade kept, as "factor direction levels: text", for reports."""
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.label is None

    @property
    def label_correct(self) -> bool:
        return self.label == self.expected_label

    @property
    def mixup(self) -> bool:
        """A study in people called an animal or lab study, or the reverse."""
        return (
            self.expected_in_people is not None
            and self.in_people is not None
            and self.expected_in_people != self.in_people
        )

    @property
    def both_gradable(self) -> bool:
        return self.expected_level is not None and self.level is not None

    @property
    def no_conflicts_concern(self) -> bool:
        """A funding concern that is a whole no-conflicts statement, which isn't a concern
        (#67 review). Uses the Grader's own test, so "Industry funded it; the authors declare no
        conflicts" doesn't count."""
        return self.funding_concern is not None and declared_conflicts(self.funding_concern) is None


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


@dataclass(frozen=True)
class Scores:
    papers: int
    gradable: int
    """Papers the labels call gradable."""
    failed: int
    decided_by_rule: int
    design_label: float | None
    """Papers with the right design category or not-gradable reason, as a share of all papers."""
    mixups: int
    """Studies in people called animal or lab studies, or the reverse. Any one blocks."""
    level_scored: int
    """Papers both the label and the Grader call gradable, which the level scores cover."""
    level_exact: float | None
    level_within_one: float | None
    funding_concerns: int
    no_conflicts_concerns: int
    """Funding concerns that only say there are no conflicts (#67 review)."""
    wrong_label_pmids: tuple[str, ...] = field(default=())
    mixup_pmids: tuple[str, ...] = field(default=())
    off_by_two_pmids: tuple[str, ...] = field(default=())
    no_conflicts_concern_pmids: tuple[str, ...] = field(default=())


def score(results: Sequence[PaperResult]) -> Scores:
    scored = [r for r in results if r.both_gradable]
    exact = sum(r.level == r.expected_level for r in scored)
    off_by_two = [r for r in scored if abs((r.level or 0) - (r.expected_level or 0)) > 1]
    wrong = [r for r in results if not r.label_correct]
    mixups = [r for r in results if r.mixup]
    concerns = [r for r in results if r.funding_concern is not None]
    no_conflicts = [r for r in concerns if r.no_conflicts_concern]
    return Scores(
        papers=len(results),
        gradable=sum(r.expected_level is not None for r in results),
        failed=sum(r.failed for r in results),
        decided_by_rule=sum(r.decided_by == "rule" for r in results),
        design_label=_ratio(len(results) - len(wrong), len(results)),
        mixups=len(mixups),
        level_scored=len(scored),
        level_exact=_ratio(exact, len(scored)),
        level_within_one=_ratio(len(scored) - len(off_by_two), len(scored)),
        funding_concerns=len(concerns),
        no_conflicts_concerns=len(no_conflicts),
        wrong_label_pmids=tuple(r.pmid for r in wrong),
        mixup_pmids=tuple(r.pmid for r in mixups),
        off_by_two_pmids=tuple(r.pmid for r in off_by_two),
        no_conflicts_concern_pmids=tuple(r.pmid for r in no_conflicts),
    )


def approved_rows(rows: Sequence[Row]) -> list[Row]:
    """Only approved labels count towards scores (`README.md`)."""
    return [row for row in rows if row["label"] == "approved"]


def article(row: Row, abstract: str) -> GraderArticle:
    """The row as the Grader sees an article. The ID only labels the call."""
    return GraderArticle(
        id=0,
        title=row["title"],
        abstract=abstract,
        publication_types=tuple(row["publication_types"]),
        grant_agencies=tuple(row["grant_agencies"]),
    )


def _expected(row: Row) -> PaperResult:
    expected = row["expected"]
    gradable = bool(expected["gradable"])
    label = design_label(gradable, expected["design_category"], expected["not_gradable"])
    if label is None:
        raise ValueError(f"PMID {row['pmid']} has no expected design or not-gradable reason")
    return PaperResult(
        pmid=row["pmid"],
        expected_label=label,
        expected_in_people=in_people(expected["design_category"], expected["review_includes"]),
        expected_level=expected["level"] if gradable else None,
    )


def grade(client: ModelClient, prompt: Prompt, row: Row, abstract: str) -> PaperResult:
    """One paper's grade. `StopRun` propagates, because the eval can't finish without it."""
    base = _expected(row)
    paper = article(row, abstract)
    rule = apply_rules(paper)
    if rule is not None:
        return replace(base, label=rule.not_gradable, decided_by="rule", reason=rule.reason)
    try:
        request = CallRequest(EVAL_RUN_ID, prompt, prompt_inputs(paper))
        decision, _ = ask_model(client, paper, request)
    except ModelCallError as exc:
        return replace(base, error=str(exc)[:MAX_ERROR_LENGTH] or type(exc).__name__)
    if not isinstance(decision, Grade):
        return replace(
            base, label=decision.not_gradable, decided_by="model", reason=decision.reason
        )
    concern = next((r.text for r in decision.reasons if r.factor == FUNDING), None)
    return replace(
        base,
        label=decision.design_category,
        decided_by="model",
        in_people=in_people(decision.design_category, decision.review_includes),
        level=decision.level,
        funding_concern=concern,
        funding_lowered=decision.funding_lowered,
        reason=decision.reason,
        starting_level=decision.starting_level,
        moves=tuple(f"{r.factor} {r.direction} {r.levels}: {r.text}" for r in decision.reasons),
    )


def run_eval(
    client: ModelClient,
    prompt: Prompt,
    rows: Sequence[Row],
    abstracts: Mapping[str, str],
    progress: Callable[[int, int], None] | None = None,
) -> list[PaperResult]:
    """Every row's grade, in dataset order."""
    if prompt.stage != STAGE:
        raise ValueError(f"The Grader eval needs a {STAGE} prompt, not {prompt.name}")
    results = []
    for number, row in enumerate(rows, start=1):
        results.append(grade(client, prompt, row, abstracts[row["pmid"]]))
        if progress is not None:
            progress(number, len(rows))
    return results


def report(
    prompt: Prompt, scores: Scores, results: Sequence[PaperResult], cost_usd: Decimal
) -> dict[str, Any]:
    """The run as JSON. It leaves out abstracts, which may not be reusable, but keeps the model's
    reasons and funding concerns, which may quote them: keep reports outside the repo."""
    return {
        "prompt": prompt.name,
        "prompt_version": prompt.version,
        "model": prompt.model,
        "cost_usd": str(cost_usd),
        "scores": asdict(scores),
        "papers": [asdict(result) for result in results],
    }
