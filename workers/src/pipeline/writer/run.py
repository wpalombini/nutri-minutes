"""Writer runs: a plain-English summary, one article at a time, for the articles the Extractor
extracted.

The model reads the extraction with the grade, its reasons and the funding facts, and
`writing.py` checks what it wrote against them. Each summary, its limits and the article's
`article_stages` row are stored in one transaction, so an interrupted run leaves no half-written
article and a later run picks up what it didn't reach. Summaries are unchecked drafts: nothing
publishes before the Fact-Checker and the Hype Detector pass them. The rules every agent follows
are in docs/agents.md.

An article's current extraction is its latest, provided it was made from the article's current
grade. Its summary is current while it was written from that extraction; after a re-extraction
the old summary is stale, so the next run writes the article again. An article that failed is
tried again once it has an extraction newer than the run that failed it.

The run loop follows the Extractor's (`pipeline.extractor.run`) on purpose; the agents can share
it once the common part is clear.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Engine, text

from pipeline.env import int_env
from pipeline.extractor.run import design_text
from pipeline.models import CallRequest, ModelCallError, ModelClient, Prompt, StopRun
from pipeline.notify import Alert, Notifier, Severity
from pipeline.runs import (
    AgentLock,
    LockLost,
    Run,
    agent_lock,
    error_text,
    find_running,
    finish_run,
    save_progress,
    start_run,
)
from pipeline.writer.writing import Draft, ReplyError, Source, limit_range, parse_reply

logger = logging.getLogger(__name__)

AGENT = "writer"
STAGE = "writer"
"""The model client's budget stage. Its budget comes from `MODEL_BUDGET_USD_WRITER`."""
PROMPT_NAME = "writer/write"
DEFAULT_BUDGET_USD = Decimal("2.50")
"""Per run, unless `MODEL_BUDGET_USD_WRITER` sets another. An estimate until the eval measures the
cost per article; a spent budget stops the run, and the rest wait for the next."""
COUNT_KEYS = ("selected", "written", "failed")
MAX_ERROR_LENGTH = 500
REPLY_ATTEMPTS = 3
"""Calls per article when replies match the schema but fail the checks. The client retries other
failures itself."""
CHECK_FAILURE = (
    "<check_failure>Your previous reply for this paper was rejected by the service's check: "
    "{reason}. Reply again in full, with this fixed.</check_failure>"
)
LEVEL_NAMES = {1: "very low", 2: "low", 3: "moderate", 4: "high"}
FIXED_LIMITS = {
    "non_randomised_trial": (
        "People weren't put into groups by chance, so other differences between the groups may "
        "explain the result."
    ),
    "observational": (
        "It can't show cause and effect. It found a link, and other differences between the "
        "people in it may explain that link."
    ),
    "animal": "It was done in animals. Results in animals often don't carry over to people.",
    "lab": "It was done on cells or tissue in a lab, not in people.",
}
"""The study page's fixed first "does not show" item for each design
(design/components/limits-block.md). The app shows it; the Writer is told it so it doesn't repeat
it."""
MEASURE_NAMES = {
    "risk_ratio": "Risk ratio",
    "odds_ratio": "Odds ratio",
    "hazard_ratio": "Hazard ratio",
    "rate_ratio": "Rate ratio",
    "mean_difference": "Mean difference",
    "risk_difference": "Risk difference",
    "standardised_mean_difference": "Standardised mean difference",
}


@dataclass(frozen=True)
class WriterSettings:
    max_articles: int = 1000
    """The most articles one run looks at. The rest wait for the next run."""

    @classmethod
    def from_env(cls) -> WriterSettings:
        return cls(max_articles=int_env("WRITER_MAX_ARTICLES", 1000, 1))


@dataclass(frozen=True)
class RunResult:
    run_id: int
    status: str


@dataclass(frozen=True)
class Effect:
    measure: str
    estimate: Decimal
    ci_lower: Decimal | None
    ci_upper: Decimal | None
    ci_level: Decimal | None
    unit: str | None
    outcome_label: str
    comparison_label: str
    lower_label: str
    higher_label: str
    quote: str


@dataclass(frozen=True)
class WriterArticle:
    id: int
    title: str
    abstract: str
    extraction_id: int
    source_basis: str
    population: str
    population_quote: str
    intervention: str
    intervention_quote: str
    comparator: str | None
    comparator_quote: str | None
    effect: Effect | None
    facts: tuple[tuple[str, str, str], ...]
    """Each fact as (kind, fact, quote), in order."""
    design_category: str
    design: str
    level: int
    reasons: tuple[tuple[str, str, int, str], ...]
    """Each grade reason as (factor, direction, levels, reason), in order."""
    funder: str | None
    funder_type: str
    funder_sells_product: str
    conflicts: str | None
    may_reuse_abstract: bool
    """Whether every source's current licence allows reuse. False when no licence is known."""


def _number(value: Decimal) -> str:
    return format(value, "f")


def _effect_text(effect: Effect | None) -> str:
    if effect is None:
        return "No effect size was extracted for the main outcome."
    unit = f" {effect.unit}" if effect.unit else ""
    lines = [f"{MEASURE_NAMES[effect.measure]} {_number(effect.estimate)}{unit}"]
    if effect.ci_lower is not None and effect.ci_upper is not None and effect.ci_level:
        lines[0] += (
            f", {_number(effect.ci_level)}% confidence interval {_number(effect.ci_lower)}{unit} "
            f"to {_number(effect.ci_upper)}{unit}"
        )
    else:
        lines[0] += ", no confidence interval reported"
    lines += [
        f"Outcome: {effect.outcome_label}",
        f"Comparison: {effect.comparison_label}",
        f"Below no difference means: {effect.lower_label}",
        f"Above no difference means: {effect.higher_label}",
        f"Quote: {effect.quote}",
    ]
    return "\n".join(lines)


def _facts_text(article: WriterArticle) -> str:
    lines = [
        f"- population: {article.population} (quote: {article.population_quote})",
        f"- intervention: {article.intervention} (quote: {article.intervention_quote})",
    ]
    if article.comparator:
        lines.append(f"- comparator: {article.comparator} (quote: {article.comparator_quote})")
    lines += [f"- {kind}: {fact} (quote: {quote})" for kind, fact, quote in article.facts]
    return "\n".join(lines)


def _reasons_text(article: WriterArticle) -> str:
    if not article.reasons:
        return "None: the grade is its starting level for this design."
    lines = []
    for factor, direction, levels, reason in article.reasons:
        move = f"{direction} {levels} level{'s' if levels != 1 else ''}" if levels else "concern"
        lines.append(f"- {factor.replace('_', ' ')}, {move}: {reason}")
    return "\n".join(lines)


def _funding_text(article: WriterArticle) -> str:
    if article.funder_type == "not_stated":
        funding = "Funding: not stated in the abstract."
    else:
        funder = article.funder or "not named"
        funding = f"Funder: {funder} ({article.funder_type.replace('_', ' ')})."
    sells = {"yes": "yes", "no": "no", "unknown": "not known"}[article.funder_sells_product]
    conflicts = article.conflicts or "none stated"
    return f"{funding}\nFunder sells the product tested: {sells}.\nConflicts: {conflicts}."


def prompt_inputs(article: WriterArticle) -> dict[str, str]:
    """The template's inputs. The prompt must use exactly these placeholders. `check_failure` is
    empty on the first call; `ask_model` fills it when asking again."""
    low, high = limit_range(article.design_category in FIXED_LIMITS)
    return {
        "title": article.title,
        "design": article.design,
        "grade": f"{LEVEL_NAMES[article.level]} certainty ({article.level} of 4)",
        "grade_reasons": _reasons_text(article),
        "funding": _funding_text(article),
        "main_effect": _effect_text(article.effect),
        "facts": _facts_text(article),
        "fixed_limit": FIXED_LIMITS.get(article.design_category, "none"),
        "limit_count": f"{low} to {high}",
        "abstract": article.abstract,
        "check_failure": "",
    }


def source_for(article: WriterArticle) -> Source:
    """What `parse_reply` checks this article's summary against."""
    numbers_text = [
        article.population,
        article.population_quote,
        article.intervention,
        article.intervention_quote,
        article.comparator or "",
        article.comparator_quote or "",
    ]
    numbers_text += [part for _, fact, quote in article.facts for part in (fact, quote)]
    effect_numbers: list[Decimal] = []
    effect = article.effect
    if effect is not None:
        numbers_text += [
            effect.unit or "",
            effect.outcome_label,
            effect.comparison_label,
            effect.lower_label,
            effect.higher_label,
            effect.quote,
        ]
        effect_numbers = [
            n
            for n in (effect.estimate, effect.ci_lower, effect.ci_upper, effect.ci_level)
            if n is not None
        ]
    return Source(
        numbers_text=tuple(t for t in numbers_text if t),
        effect_numbers=tuple(effect_numbers),
        has_absolute=any(kind == "absolute" for kind, _, _ in article.facts),
        fixed_limit=FIXED_LIMITS.get(article.design_category),
        funder_sells_product=article.funder_sells_product == "yes",
        abstract=article.abstract,
        may_reuse_abstract=article.may_reuse_abstract,
    )


SELECT_ARTICLES = """
SELECT a.id, a.title, a.abstract, x.id AS extraction_id, x.source_basis,
       x.population, x.population_quote,
       x.intervention,
       x.intervention_quote, x.comparator, x.comparator_quote, x.measure, x.estimate, x.ci_lower,
       x.ci_upper, x.ci_level, x.unit, x.outcome_label, x.comparison_label, x.lower_label,
       x.higher_label, x.effect_quote, g.id AS grade_id, g.design_category, g.review_includes,
       g.level, g.funder, g.funder_type, g.funder_sells_product, g.conflicts,
       COALESCE((
           SELECT bool_and(l.full_text_reuse_allowed) FROM (
               SELECT DISTINCT ON (source) full_text_reuse_allowed FROM article_licences
               WHERE article_id = a.id ORDER BY source, last_seen_at DESC, id DESC
           ) l
       ), false) AS may_reuse_abstract
FROM articles a
JOIN LATERAL (
    SELECT d.in_scope FROM triage_decisions d WHERE d.article_id = a.id ORDER BY d.id DESC LIMIT 1
) latest ON latest.in_scope
JOIN LATERAL (
    SELECT * FROM evidence_grades e WHERE e.article_id = a.id ORDER BY e.id DESC LIMIT 1
) g ON g.level IS NOT NULL
JOIN LATERAL (
    SELECT * FROM extractions e WHERE e.article_id = a.id ORDER BY e.id DESC LIMIT 1
) x ON x.grade_id = g.id
"""
"""Articles whose latest Triage decision is in scope, whose latest grade is a grade and whose
latest extraction was made from it, with that extraction and grade. A licence counts only when
every source's current licence allows reuse (docs/database.md); none known means no reuse."""
PENDING = text(
    SELECT_ARTICLES  # noqa: S608 (fixed text)
    + "LEFT JOIN article_stages s ON s.article_id = a.id AND s.agent = :agent "
    "WHERE s.article_id IS NULL OR (s.status = 'done' AND (SELECT m.extraction_id FROM summaries m "
    "WHERE m.article_id = a.id ORDER BY m.id DESC LIMIT 1) IS DISTINCT FROM x.id) "
    "OR (s.status = 'failed' AND (SELECT r.started_at FROM pipeline_runs r "
    "WHERE r.id = s.run_id) < x.created_at) "
    "ORDER BY a.id LIMIT :limit"
)
CHOSEN = text(SELECT_ARTICLES + "WHERE a.id = ANY(:ids) ORDER BY a.id")
FACTS = text(
    "SELECT extraction_id, kind, fact, quote FROM extraction_facts "
    "WHERE extraction_id = ANY(:ids) ORDER BY extraction_id, position"
)
REASONS = text(
    "SELECT grade_id, factor, direction, levels, reason FROM evidence_grade_reasons "
    "WHERE grade_id = ANY(:ids) ORDER BY grade_id, position"
)
CURRENT_EXTRACTION = text(
    "SELECT x.id FROM extractions x WHERE x.article_id = :article_id "
    "AND x.grade_id = (SELECT g.id FROM evidence_grades g WHERE g.article_id = :article_id "
    "ORDER BY g.id DESC LIMIT 1) AND x.id = (SELECT max(y.id) FROM extractions y "
    "WHERE y.article_id = :article_id)"
)
CALL_ARTICLE = text("SELECT article_id FROM model_calls WHERE id = :id")
UPSERT_STAGE = text(
    "INSERT INTO article_stages (article_id, agent, status, run_id, error) "
    "VALUES (:article_id, :agent, :status, :run_id, :error) "
    "ON CONFLICT (article_id, agent) DO UPDATE SET status = EXCLUDED.status, "
    "run_id = EXCLUDED.run_id, error = EXCLUDED.error, updated_at = now()"
)
INSERT_SUMMARY = text(
    "INSERT INTO summaries (article_id, run_id, extraction_id, model_call_id, source_basis, "
    "headline, body, result_sentence, absolute_sentence) VALUES (:article_id, :run_id, "
    ":extraction_id, :model_call_id, :source_basis, :headline, :body, :result_sentence, "
    ":absolute_sentence) RETURNING id"
)
INSERT_LIMIT = text(
    "INSERT INTO summary_limits (summary_id, position, statement) "
    "VALUES (:summary_id, :position, :statement)"
)


def _effect(row: Any) -> Effect | None:
    if row.measure is None:
        return None
    return Effect(
        measure=row.measure,
        estimate=row.estimate,
        ci_lower=row.ci_lower,
        ci_upper=row.ci_upper,
        ci_level=row.ci_level,
        unit=row.unit,
        outcome_label=row.outcome_label,
        comparison_label=row.comparison_label,
        lower_label=row.lower_label,
        higher_label=row.higher_label,
        quote=row.effect_quote,
    )


def select_articles(
    engine: Engine, limit: int, article_ids: Sequence[int] | None = None
) -> list[WriterArticle]:
    """Extracted articles the Writer hasn't handled, or whose summary is stale after a
    re-extraction, oldest first; or the chosen ones for a re-run. Chosen articles without a
    current extraction are left out."""
    with engine.connect() as conn:
        if article_ids is not None:
            rows = list(conn.execute(CHOSEN, {"ids": list(article_ids)}))
        else:
            rows = list(conn.execute(PENDING, {"agent": AGENT, "limit": limit}))
        facts: dict[int, list[tuple[str, str, str]]] = {}
        for f in conn.execute(FACTS, {"ids": [r.extraction_id for r in rows]}):
            facts.setdefault(f.extraction_id, []).append((f.kind, f.fact, f.quote))
        reasons: dict[int, list[tuple[str, str, int, str]]] = {}
        for g in conn.execute(REASONS, {"ids": [r.grade_id for r in rows]}):
            reasons.setdefault(g.grade_id, []).append((g.factor, g.direction, g.levels, g.reason))
    return [
        WriterArticle(
            id=int(row.id),
            title=row.title,
            abstract=row.abstract or "",
            extraction_id=int(row.extraction_id),
            source_basis=row.source_basis,
            population=row.population,
            population_quote=row.population_quote,
            intervention=row.intervention,
            intervention_quote=row.intervention_quote,
            comparator=row.comparator,
            comparator_quote=row.comparator_quote,
            effect=_effect(row),
            facts=tuple(facts.get(row.extraction_id, ())),
            design_category=row.design_category,
            design=design_text(str(row.design_category), row.review_includes),
            level=int(row.level),
            reasons=tuple(reasons.get(row.grade_id, ())),
            funder=row.funder,
            funder_type=row.funder_type,
            funder_sells_product=row.funder_sells_product,
            conflicts=row.conflicts,
            may_reuse_abstract=bool(row.may_reuse_abstract),
        )
        for row in rows
    ]


def _set_stage(conn: Connection, run: Run, article_id: int, error: str | None) -> None:
    conn.execute(
        UPSERT_STAGE,
        {
            "article_id": article_id,
            "agent": AGENT,
            "status": "failed" if error is not None else "done",
            "run_id": run.id,
            "error": error,
        },
    )


def _store(conn: Connection, run: Run, article: WriterArticle, draft: Draft, call_id: int) -> None:
    # The extraction must still be the article's current one, and the call about this article,
    # so a summary never points at another article's facts or ones replaced while the model was
    # writing. A re-extraction in the meantime fails the article here; the next run writes it again
    # from the new extraction.
    current = conn.execute(CURRENT_EXTRACTION, {"article_id": article.id}).scalar_one_or_none()
    if current != article.extraction_id:
        raise RuntimeError(
            f"Extraction {article.extraction_id} is no longer the article's current extraction"
        )
    call_article = conn.execute(CALL_ARTICLE, {"id": call_id}).scalar_one_or_none()
    if call_article != article.id:
        raise RuntimeError(f"Model call {call_id} isn't about article {article.id}")
    summary_id = conn.execute(
        INSERT_SUMMARY,
        {
            "article_id": article.id,
            "run_id": run.id,
            "extraction_id": article.extraction_id,
            "model_call_id": call_id,
            "source_basis": article.source_basis,  # always the extraction's own
            "headline": draft.headline,
            "body": draft.body,
            "result_sentence": draft.result_sentence,
            "absolute_sentence": draft.absolute_sentence,
        },
    ).scalar_one()
    for position, statement in enumerate(draft.limits, start=1):
        conn.execute(
            INSERT_LIMIT, {"summary_id": summary_id, "position": position, "statement": statement}
        )
    _set_stage(conn, run, article.id, None)


def ask_model(
    client: ModelClient, article: WriterArticle, request: CallRequest
) -> tuple[Draft, int]:
    """Ask the model, calling again with the reason when a reply fails the checks, up to
    `REPLY_ATTEMPTS` calls. Returns the draft and the call it came from. Used by runs and the
    eval."""
    source = source_for(article)
    for attempt in range(1, REPLY_ATTEMPTS + 1):
        result = client.call(request)
        try:
            return parse_reply(result.reply, source), result.call_id
        except ReplyError as exc:
            if attempt == REPLY_ATTEMPTS:
                raise
            logger.info(
                "Writer run %d: asking again after call %d: %s",
                request.run_id,
                result.call_id,
                exc,
            )
            note = CHECK_FAILURE.format(reason=str(exc).rstrip("."))
            request = replace(request, inputs={**request.inputs, "check_failure": note})
    raise AssertionError("unreachable")  # pragma: no cover


def _write_one(
    engine: Engine,
    lock: AgentLock,
    client: ModelClient,
    prompt: Prompt,
    run: Run,
    article: WriterArticle,
) -> str:
    """Write one article's summary and store it. Returns the count it adds to.

    `StopRun` propagates and leaves the article untouched, so the next run picks it up.
    """
    draft: Draft | None = None
    call_id = 0
    failure: str | None = None
    if not article.abstract.strip():
        failure = "No abstract to write from"
    else:
        try:
            draft, call_id = ask_model(
                client, article, CallRequest(run.id, prompt, prompt_inputs(article), article.id)
            )
        except ModelCallError as exc:
            failure = str(exc)[:MAX_ERROR_LENGTH] or type(exc).__name__
    if failure is not None:
        logger.warning("Writer run %d: article %d failed: %s", run.id, article.id, failure)

    outcome = "written" if draft is not None else "failed"
    counts = dict(run.counts)
    counts[outcome] += 1
    with engine.begin() as conn:
        if draft is not None:
            _store(conn, run, article, draft, call_id)
        else:
            _set_stage(conn, run, article.id, failure)
        save_progress(conn, run, {"last_article_id": article.id}, counts)
        lock.check()
    run.counts = counts
    return outcome


def _fail_article(engine: Engine, run: Run, article_id: int, exc: Exception) -> None:
    """Mark an article failed after an unexpected error, without hiding that error."""
    with engine.begin() as conn:
        _set_stage(conn, run, article_id, error_text(exc))
        counts = dict(run.counts)
        counts["failed"] += 1
        save_progress(conn, run, {"last_article_id": article_id}, counts)
    run.counts = counts


def _execute(
    engine: Engine,
    lock: AgentLock,
    client: ModelClient,
    prompt: Prompt,
    notifier: Notifier,
    run: Run,
    articles: list[WriterArticle],
) -> str:
    for key in COUNT_KEYS:
        run.counts.setdefault(key, 0)
    run.counts["selected"] = len(articles)
    try:
        for article in articles:
            try:
                _write_one(engine, lock, client, prompt, run, article)
            except StopRun, LockLost:
                raise
            except Exception as exc:
                # One bad article must not fail the run, including a row the database rejects.
                # If even marking it failed doesn't work, the run stops below.
                logger.exception("Writer run %d: article %d failed", run.id, article.id)
                _fail_article(engine, run, article.id, exc)
    except LockLost:
        logger.error("Writer run %d lost its lock connection", run.id)
        notifier.send(
            Alert(
                Severity.WARNING,
                f"Writer run {run.id} stopped",
                "It lost its database lock connection. The next run picks up its articles.",
            )
        )
        raise
    except Exception as exc:
        logger.exception("Writer run %d failed", run.id)
        notifier.send(Alert(Severity.ERROR, f"Writer run {run.id} failed", error_text(exc)))
        with engine.begin() as conn:
            finish_run(conn, run, "failed", error_text(exc))
        return "failed"

    status = "partial" if run.counts["failed"] else "succeeded"
    with engine.begin() as conn:
        finish_run(conn, run, status)
    logger.info("Writer run %d %s: %s", run.id, status, run.counts)
    if status == "partial":
        every_article = run.counts["failed"] == run.counts["selected"]
        notifier.send(
            Alert(
                Severity.ERROR if every_article else Severity.WARNING,
                f"Writer run {run.id} finished with failed articles",
                f"{run.counts['failed']} of {run.counts['selected']} articles failed. Their "
                "errors are in article_stages. Fix the cause, then re-run those articles.",
            )
        )
    return status


def run_writer(
    engine: Engine,
    client: ModelClient,
    prompt: Prompt,
    notifier: Notifier,
    settings: WriterSettings,
    article_ids: Sequence[int] | None = None,
) -> RunResult | None:
    """Run the Writer once. Returns None if another worker holds the lock.

    Without `article_ids`, the run takes extracted articles with no current summary, up to the
    setting's limit. With them, it writes those articles again, including failed ones, adding
    new summaries beside the old.
    """
    if prompt.stage != STAGE:
        raise ValueError(f"The Writer needs a {STAGE} prompt, not {prompt.name}")
    with agent_lock(engine, AGENT) as lock:
        if lock is None:
            logger.info("Another Writer run holds the lock, so this one is exiting")
            return None

        with engine.begin() as conn:
            dead = find_running(conn, AGENT)
            if dead is not None:
                finish_run(conn, dead, "failed", "Interrupted. A later run took its articles.")
        if dead is not None:
            notifier.send(
                Alert(
                    Severity.WARNING,
                    f"Writer run {dead.id} was interrupted",
                    "It was marked failed, and this run picks up the articles it didn't reach.",
                )
            )

        articles = select_articles(engine, settings.max_articles, article_ids)
        if article_ids is not None and len(articles) < len(article_ids):
            chosen = {a.id for a in articles}
            skipped = sorted(set(article_ids) - chosen)
            logger.warning("Skipping articles without a current extraction: %s", skipped)
        parameters = {
            "prompt": prompt.name,
            "prompt_version": prompt.version,
            "model": prompt.model,
            "max_articles": settings.max_articles,
            "article_ids": sorted(article_ids) if article_ids is not None else None,
        }
        with engine.begin() as conn:
            run = start_run(conn, AGENT, parameters)
        logger.info("Starting Writer run %d with %d articles", run.id, len(articles))
        status = _execute(engine, lock, client, prompt, notifier, run, articles)
        return RunResult(run.id, status)
