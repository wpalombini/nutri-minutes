"""Run the Extractor on the approved eval papers and score its extractions (ADR 0005).

Each paper goes through production's path: the Grader's fields from the dataset become the same
prompt inputs production builds from a grade, the model is called through the same client, and
the reply passes the same checks (`pipeline.extractor.extraction`), asked again up to three times.

Scores (`README.md`):
- **Main effect right:** the measure, estimate, limits and level match `expected` or one of the
  `also_accepted` alternatives, numbers written exactly as the label writes them. "No main
  effect" is right when a label says so.
- **Main effect found:** the extraction has a main effect exactly when a label does, whatever its
  numbers.
- **Sign errors:** a main effect whose estimate is a label's with the opposite sign, the worst
  error, since readers would see the result reversed.
- **Absolute numbers and limits found:** the share of papers the labels say give absolute numbers,
  or state a limit, whose extraction has an `absolute` or `limitation` fact.

A failed paper (three replies that fail the checks, or a failed call) counts as wrong everywhere,
so the baseline check also caps failures. The unit is compared but reported only, since the same
unit can be written several ways.
"""

import hashlib
import json
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from evals.abstracts import Row
from pipeline.extractor.extraction import NO_MEASURE, Extraction, MainEffect
from pipeline.extractor.run import (
    MAX_ERROR_LENGTH,
    STAGE,
    ExtractorArticle,
    ask_model,
    design_text,
    prompt_inputs,
)
from pipeline.models import CallRequest, CallResult, ModelCallError, ModelClient, Prompt

EVAL_RUN_ID = 0
"""Eval calls belong to no pipeline run. The in-memory call log keys the budget on this."""
NUMBER_FIELDS = ("estimate", "ci_lower", "ci_upper", "ci_level")

type Target = Mapping[str, Any]
"""A labelled main effect: `measure`, and the number fields and unit it constrains. In `expected`
every field is present; an alternative leaves out the fields it doesn't constrain."""


def approved_rows(rows: Sequence[Row]) -> list[Row]:
    """Only approved labels count towards scores (`README.md`)."""
    return [row for row in rows if row["label"] == "approved"]


def labels_hash(rows: Sequence[Row]) -> str:
    """A short hash of the labels the scores depend on, so a relabel that keeps the counts still
    marks the baseline stale."""
    labels = [[row["pmid"], row["expected"], row["also_accepted"]] for row in rows]
    text = json.dumps(labels, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def article(row: Row, abstract: str) -> ExtractorArticle:
    """The row as the Extractor sees an article, with the Grader's fields from the dataset. The
    IDs only label the call."""
    grader = row["grader"]
    return ExtractorArticle(
        id=0,
        title=row["title"],
        abstract=abstract,
        publication_types=tuple(row["publication_types"]),
        grade_id=0,
        design=design_text(grader["design_category"], grader["review_includes"]),
        main_outcome=grader["main_outcome"],
        participants=grader["participants"],
        duration=grader["duration"],
        population=grader["population"],
    )


def _written(value: Decimal | None) -> str | None:
    """A number as the extraction stores it: as written, never in exponent form."""
    return None if value is None else format(value, "f")


def _matches(effect: MainEffect | None, target: Target) -> bool:
    if target["measure"] == NO_MEASURE:
        return effect is None
    if effect is None or effect.measure != target["measure"]:
        return False
    return all(
        _written(getattr(effect, key)) == target[key] for key in NUMBER_FIELDS if key in target
    )


def _sign_error(effect: MainEffect | None, target: Target) -> bool:
    """The estimate is the target's with the opposite sign."""
    wanted = target.get("estimate")
    if effect is None or wanted is None or effect.measure != target["measure"]:
        return False
    return effect.estimate != 0 and effect.estimate == -Decimal(wanted)


def unit_form(unit: str | None) -> str | None:
    """A unit as compared: compatibility form ("m²" as "m2"), case and spaces ignored."""
    if unit is None:
        return None
    return "".join(unicodedata.normalize("NFKC", unit).casefold().split()) or None


@dataclass(frozen=True)
class PaperResult:
    pmid: str
    expected_measure: str
    expected_effect: bool
    """Whether `expected` has a main effect."""
    expected_absolute: bool
    expected_limitation: bool
    measure: str | None = None
    """None when the paper failed."""
    estimate: str | None = None
    ci_lower: str | None = None
    ci_upper: str | None = None
    ci_level: str | None = None
    unit: str | None = None
    effect_quote: str | None = None
    effect_right: bool = False
    effect_found_right: bool = False
    """The extraction has a main effect exactly when a label does."""
    sign_error: bool = False
    unit_right: bool | None = None
    """Whether the unit matches the label the effect matched. None when there is nothing to
    compare: no match, or a label that doesn't constrain the unit."""
    absolute: bool = False
    limitation: bool = False
    facts: tuple[str, ...] = ()
    """Each fact as "kind: fact", for reports."""
    calls: int = 0
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.measure is None


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


@dataclass(frozen=True)
class Scores:
    papers: int
    with_effect: int
    """Papers whose `expected` has a main effect."""
    failed: int
    calls: int
    asked_again: int
    """Papers that needed more than one call."""
    effect_right: float | None
    effect_found: float | None
    sign_errors: int
    """More than the baseline blocks."""
    with_absolute: int
    absolute_found: float | None
    absolute_extra: int
    """Absolute facts where the label expects none."""
    with_limitation: int
    limitation_found: float | None
    limitation_extra: int
    failed_pmids: tuple[str, ...] = field(default=())
    missed_effect_pmids: tuple[str, ...] = field(default=())
    """No main effect, where every label has one."""
    extra_effect_pmids: tuple[str, ...] = field(default=())
    """A main effect, where a label says there is none and no label accepts one."""
    wrong_effect_pmids: tuple[str, ...] = field(default=())
    """A main effect where one is expected, with the wrong measure or numbers."""
    sign_error_pmids: tuple[str, ...] = field(default=())
    unit_mismatch_pmids: tuple[str, ...] = field(default=())
    missed_absolute_pmids: tuple[str, ...] = field(default=())
    missed_limitation_pmids: tuple[str, ...] = field(default=())


def score(results: Sequence[PaperResult]) -> Scores:
    done = [r for r in results if not r.failed]
    absolute = [r for r in results if r.expected_absolute]
    limitation = [r for r in results if r.expected_limitation]
    return Scores(
        papers=len(results),
        with_effect=sum(r.expected_effect for r in results),
        failed=len(results) - len(done),
        calls=sum(r.calls for r in results),
        asked_again=sum(r.calls > 1 for r in results),
        effect_right=_ratio(sum(r.effect_right for r in results), len(results)),
        effect_found=_ratio(sum(r.effect_found_right for r in results), len(results)),
        sign_errors=sum(r.sign_error for r in results),
        with_absolute=len(absolute),
        absolute_found=_ratio(sum(r.absolute for r in absolute), len(absolute)),
        absolute_extra=sum(r.absolute and not r.expected_absolute for r in results),
        with_limitation=len(limitation),
        limitation_found=_ratio(sum(r.limitation for r in limitation), len(limitation)),
        limitation_extra=sum(r.limitation and not r.expected_limitation for r in results),
        failed_pmids=tuple(r.pmid for r in results if r.failed),
        missed_effect_pmids=tuple(
            r.pmid for r in done if not r.effect_found_right and r.measure == NO_MEASURE
        ),
        extra_effect_pmids=tuple(
            r.pmid for r in done if not r.effect_found_right and r.measure != NO_MEASURE
        ),
        wrong_effect_pmids=tuple(
            r.pmid
            for r in done
            if r.effect_found_right and not r.effect_right and r.measure != NO_MEASURE
        ),
        sign_error_pmids=tuple(r.pmid for r in results if r.sign_error),
        unit_mismatch_pmids=tuple(r.pmid for r in results if r.unit_right is False),
        missed_absolute_pmids=tuple(r.pmid for r in absolute if not r.absolute),
        missed_limitation_pmids=tuple(r.pmid for r in limitation if not r.limitation),
    )


def _targets(row: Row) -> list[Target]:
    expected = row["expected"]
    first = {key: expected[key] for key in ("measure", *NUMBER_FIELDS, "unit")}
    return [MappingProxyType(first), *(MappingProxyType(alt) for alt in row["also_accepted"])]


def _expected(row: Row) -> PaperResult:
    expected = row["expected"]
    return PaperResult(
        pmid=row["pmid"],
        expected_measure=expected["measure"],
        expected_effect=expected["measure"] != NO_MEASURE,
        expected_absolute=bool(expected["has_absolute"]),
        expected_limitation=bool(expected["has_limitation"]),
    )


def compare(base: PaperResult, targets: Sequence[Target], extraction: Extraction) -> PaperResult:
    """Score one extraction against the paper's labels."""
    effect = extraction.effect
    matched = next((t for t in targets if _matches(effect, t)), None)
    has_effect = effect is not None
    unit_right = None
    if matched is not None and effect is not None and "unit" in matched:
        unit_right = unit_form(effect.unit) == unit_form(matched["unit"])
    kinds = {fact.kind for fact in extraction.facts}
    return replace(
        base,
        measure=effect.measure if effect is not None else NO_MEASURE,
        estimate=_written(effect.estimate) if effect is not None else None,
        ci_lower=_written(effect.ci_lower) if effect is not None else None,
        ci_upper=_written(effect.ci_upper) if effect is not None else None,
        ci_level=_written(effect.ci_level) if effect is not None else None,
        unit=effect.unit if effect is not None else None,
        effect_quote=effect.quote if effect is not None else None,
        effect_right=matched is not None,
        effect_found_right=any((t["measure"] != NO_MEASURE) == has_effect for t in targets),
        sign_error=matched is None and any(_sign_error(effect, t) for t in targets),
        unit_right=unit_right,
        absolute="absolute" in kinds,
        limitation="limitation" in kinds,
        facts=tuple(f"{fact.kind}: {fact.fact}" for fact in extraction.facts),
    )


class _CountingClient:
    """Counts the calls `ask_model` makes for one paper."""

    def __init__(self, client: ModelClient) -> None:
        self._client = client
        self.calls = 0

    def call(self, request: CallRequest) -> CallResult:
        self.calls += 1
        return self._client.call(request)


def extract(client: ModelClient, prompt: Prompt, row: Row, abstract: str) -> PaperResult:
    """One paper's extraction, scored. `StopRun` propagates, because the eval can't finish
    without it."""
    base = _expected(row)
    paper = article(row, abstract)
    counting = _CountingClient(client)
    try:
        request = CallRequest(EVAL_RUN_ID, prompt, prompt_inputs(paper))
        extraction, _ = ask_model(counting, paper, request)
    except ModelCallError as exc:
        error = str(exc)[:MAX_ERROR_LENGTH] or type(exc).__name__
        return replace(base, calls=counting.calls, error=error)
    return replace(compare(base, _targets(row), extraction), calls=counting.calls)


def run_eval(
    client: ModelClient,
    prompt: Prompt,
    rows: Sequence[Row],
    abstracts: Mapping[str, str],
    progress: Callable[[int, int], None] | None = None,
) -> list[PaperResult]:
    """Every row's extraction, in dataset order."""
    if prompt.stage != STAGE:
        raise ValueError(f"The Extractor eval needs an {STAGE} prompt, not {prompt.name}")
    results = []
    for number, row in enumerate(rows, start=1):
        results.append(extract(client, prompt, row, abstracts[row["pmid"]]))
        if progress is not None:
            progress(number, len(rows))
    return results


def report(
    prompt: Prompt, scores: Scores, results: Sequence[PaperResult], cost_usd: Decimal
) -> dict[str, Any]:
    """The run as JSON. It leaves out abstracts, which may not be reusable, but keeps facts and
    quotes taken from them: keep reports outside the repo."""
    return {
        "prompt": prompt.name,
        "prompt_version": prompt.version,
        "model": prompt.model,
        "cost_usd": str(cost_usd),
        "scores": asdict(scores),
        "papers": [asdict(result) for result in results],
    }
