"""Extractor runs: structured facts, one article at a time, for the articles the Grader graded.

The model reads the abstract with the Grader's design and main outcome, and `extraction.py`
checks every quote and number against the abstract. Each extraction, its facts and the article's
`article_stages` row are stored in one transaction, so an interrupted run leaves no half-written
article and a later run picks up what it didn't reach. The rules every agent follows are in
docs/agents.md.

An article's current extraction is its latest, provided it was made from the article's current
grade. After a re-grade the old extraction is stale, so the next run extracts the article again.

The run loop follows the Grader's (`pipeline.grader.run`) on purpose; the three can share it once
the common part is clear.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Engine, text

from pipeline.env import int_env
from pipeline.extractor.extraction import Extraction, ReplyError, parse_reply
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

logger = logging.getLogger(__name__)

AGENT = "extractor"
STAGE = "extractor"
"""The model client's budget stage. Its budget comes from `MODEL_BUDGET_USD_EXTRACTOR`."""
PROMPT_NAME = "extractor/extract"
SOURCE_BASIS = "abstract"
"""Only abstracts are used for now; reading permitted full text is a later task."""
DEFAULT_BUDGET_USD = Decimal("2.00")
"""Per run, unless `MODEL_BUDGET_USD_EXTRACTOR` sets another. An estimate until the eval measures
the cost per article (about US$0.001 expected on Haiku 5.5). A spent budget stops the run, and
the rest wait for the next."""
COUNT_KEYS = ("selected", "with_main_effect", "without_main_effect", "failed")
MAX_ERROR_LENGTH = 500
REPLY_ATTEMPTS = 3
"""Calls per article when replies match the schema but fail the checks. The client retries other
failures itself."""


@dataclass(frozen=True)
class ExtractorSettings:
    max_articles: int = 1000
    """The most articles one run looks at. The rest wait for the next run."""

    @classmethod
    def from_env(cls) -> ExtractorSettings:
        return cls(max_articles=int_env("EXTRACTOR_MAX_ARTICLES", 1000, 1))


@dataclass(frozen=True)
class RunResult:
    run_id: int
    status: str


@dataclass(frozen=True)
class ExtractorArticle:
    id: int
    title: str
    abstract: str | None
    publication_types: tuple[str, ...]
    grade_id: int
    """The article's current grade, which the extraction is made from."""
    design: str
    main_outcome: str
    participants: int | None
    duration: str | None
    population: str | None


def prompt_inputs(article: ExtractorArticle) -> dict[str, str]:
    """The template's inputs. The prompt must use exactly these placeholders."""
    return {
        "title": article.title,
        "abstract": article.abstract or "",
        "publication_types": ", ".join(article.publication_types) or "not given",
        "design": article.design,
        "main_outcome": article.main_outcome,
        "participants": str(article.participants) if article.participants else "not stated",
        "duration": article.duration or "not stated",
        "population": article.population or "not stated",
    }


SELECT_ARTICLES = """
SELECT a.id, a.title, a.abstract, a.publication_types, g.id AS grade_id, g.design_category,
       g.review_includes, g.main_outcome, g.participants, g.duration, g.population
FROM articles a
JOIN LATERAL (
    SELECT d.in_scope FROM triage_decisions d WHERE d.article_id = a.id ORDER BY d.id DESC LIMIT 1
) latest ON latest.in_scope
JOIN LATERAL (
    SELECT * FROM evidence_grades e WHERE e.article_id = a.id ORDER BY e.id DESC LIMIT 1
) g ON g.level IS NOT NULL
"""
"""Articles whose latest Triage decision is in scope and whose latest grade is a grade, not a
"not gradable" decision, with that grade."""
PENDING = text(
    SELECT_ARTICLES  # noqa: S608 (fixed text)
    + "LEFT JOIN article_stages s ON s.article_id = a.id AND s.agent = :agent "
    "WHERE s.article_id IS NULL OR (s.status = 'done' AND (SELECT x.grade_id FROM extractions x "
    "WHERE x.article_id = a.id ORDER BY x.id DESC LIMIT 1) IS DISTINCT FROM g.id) "
    "ORDER BY a.id LIMIT :limit"
)
CHOSEN = text(SELECT_ARTICLES + "WHERE a.id = ANY(:ids) ORDER BY a.id")
CURRENT_GRADE = text(
    "SELECT g.id FROM evidence_grades g WHERE g.article_id = :article_id ORDER BY g.id DESC LIMIT 1"
)
UPSERT_STAGE = text(
    "INSERT INTO article_stages (article_id, agent, status, run_id, error) "
    "VALUES (:article_id, :agent, :status, :run_id, :error) "
    "ON CONFLICT (article_id, agent) DO UPDATE SET status = EXCLUDED.status, "
    "run_id = EXCLUDED.run_id, error = EXCLUDED.error, updated_at = now()"
)
EXTRACTION_COLUMNS = (
    "article_id",
    "run_id",
    "grade_id",
    "model_call_id",
    "source_basis",
    "population",
    "population_quote",
    "intervention",
    "intervention_quote",
    "comparator",
    "comparator_quote",
    "measure",
    "estimate",
    "ci_lower",
    "ci_upper",
    "ci_level",
    "unit",
    "outcome_label",
    "comparison_label",
    "lower_label",
    "higher_label",
    "effect_quote",
)
INSERT_EXTRACTION = text(
    f"INSERT INTO extractions ({', '.join(EXTRACTION_COLUMNS)}) "  # noqa: S608 (fixed names)
    f"VALUES ({', '.join(':' + c for c in EXTRACTION_COLUMNS)}) RETURNING id"
)
INSERT_FACT = text(
    "INSERT INTO extraction_facts (extraction_id, position, kind, fact, quote) "
    "VALUES (:extraction_id, :position, :kind, :fact, :quote)"
)


def _design(row: Any) -> str:
    design = str(row.design_category).replace("_", " ")
    if row.review_includes:
        return f"{design} of {str(row.review_includes).replace('_', ' ')}"
    return design


def _article(row: Any) -> ExtractorArticle:
    return ExtractorArticle(
        id=int(row.id),
        title=row.title,
        abstract=row.abstract,
        publication_types=tuple(row.publication_types),
        grade_id=int(row.grade_id),
        design=_design(row),
        main_outcome=row.main_outcome,
        participants=row.participants,
        duration=row.duration,
        population=row.population,
    )


def select_articles(
    engine: Engine, limit: int, article_ids: Sequence[int] | None = None
) -> list[ExtractorArticle]:
    """Graded articles the Extractor hasn't handled, or whose extraction is stale after a
    re-grade, oldest first; or the chosen ones for a re-run. Chosen articles that are out of
    scope or whose latest grade isn't a grade are left out."""
    with engine.connect() as conn:
        if article_ids is not None:
            rows = conn.execute(CHOSEN, {"ids": list(article_ids)})
        else:
            rows = conn.execute(PENDING, {"agent": AGENT, "limit": limit})
        return [_article(row) for row in rows]


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


def _store(
    conn: Connection, run: Run, article: ExtractorArticle, extraction: Extraction, call_id: int
) -> None:
    # The grade must still be the article's current one, so an extraction never points at
    # another article's grade or one replaced while the model was reading. A re-grade in the
    # meantime fails the article here; a person re-runs it.
    current = conn.execute(CURRENT_GRADE, {"article_id": article.id}).scalar_one_or_none()
    if current != article.grade_id:
        raise RuntimeError(f"Grade {article.grade_id} is no longer the article's current grade")
    effect = extraction.effect
    row: dict[str, Any] = dict.fromkeys(EXTRACTION_COLUMNS)
    row.update(
        article_id=article.id,
        run_id=run.id,
        grade_id=article.grade_id,
        model_call_id=call_id,
        source_basis=SOURCE_BASIS,
        population=extraction.population,
        population_quote=extraction.population_quote,
        intervention=extraction.intervention,
        intervention_quote=extraction.intervention_quote,
        comparator=extraction.comparator,
        comparator_quote=extraction.comparator_quote,
    )
    if effect is not None:
        row.update(
            measure=effect.measure,
            estimate=effect.estimate,
            ci_lower=effect.ci_lower,
            ci_upper=effect.ci_upper,
            ci_level=effect.ci_level,
            unit=effect.unit,
            outcome_label=effect.outcome_label,
            comparison_label=effect.comparison_label,
            lower_label=effect.lower_label,
            higher_label=effect.higher_label,
            effect_quote=effect.quote,
        )
    extraction_id = conn.execute(INSERT_EXTRACTION, row).scalar_one()
    for position, fact in enumerate(extraction.facts, start=1):
        conn.execute(
            INSERT_FACT,
            {
                "extraction_id": extraction_id,
                "position": position,
                "kind": fact.kind,
                "fact": fact.fact,
                "quote": fact.quote,
            },
        )
    _set_stage(conn, run, article.id, None)


def ask_model(
    client: ModelClient, article: ExtractorArticle, request: CallRequest
) -> tuple[Extraction, int]:
    """Ask the model, calling again when a reply fails the checks. Returns the extraction and the
    call it came from. Used by runs and, later, the eval."""
    abstract = article.abstract or ""
    for _ in range(REPLY_ATTEMPTS - 1):
        result = client.call(request)
        try:
            return parse_reply(result.reply, abstract), result.call_id
        except ReplyError as exc:
            logger.info(
                "Extractor run %d: asking again after call %d: %s",
                request.run_id,
                result.call_id,
                exc,
            )
    result = client.call(request)
    return parse_reply(result.reply, abstract), result.call_id


def _extract_one(
    engine: Engine,
    lock: AgentLock,
    client: ModelClient,
    prompt: Prompt,
    run: Run,
    article: ExtractorArticle,
) -> str:
    """Extract one article and store the result. Returns the count it adds to.

    `StopRun` propagates and leaves the article untouched, so the next run picks it up.
    """
    extraction: Extraction | None = None
    call_id = 0
    failure: str | None = None
    if not (article.abstract or "").strip():
        failure = "No abstract to extract from"
    else:
        try:
            extraction, call_id = ask_model(
                client, article, CallRequest(run.id, prompt, prompt_inputs(article), article.id)
            )
        except ModelCallError as exc:
            failure = str(exc)[:MAX_ERROR_LENGTH] or type(exc).__name__
    if failure is not None:
        logger.warning("Extractor run %d: article %d failed: %s", run.id, article.id, failure)

    if extraction is None:
        outcome = "failed"
    elif extraction.effect is not None:
        outcome = "with_main_effect"
    else:
        outcome = "without_main_effect"
    counts = dict(run.counts)
    counts[outcome] += 1
    with engine.begin() as conn:
        if extraction is not None:
            _store(conn, run, article, extraction, call_id)
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
    articles: list[ExtractorArticle],
) -> str:
    for key in COUNT_KEYS:
        run.counts.setdefault(key, 0)
    run.counts["selected"] = len(articles)
    try:
        for article in articles:
            try:
                _extract_one(engine, lock, client, prompt, run, article)
            except StopRun, LockLost:
                raise
            except Exception as exc:
                # One bad article must not fail the run, including a row the database rejects.
                # If even marking it failed doesn't work, the run stops below.
                logger.exception("Extractor run %d: article %d failed", run.id, article.id)
                _fail_article(engine, run, article.id, exc)
    except LockLost:
        logger.error("Extractor run %d lost its lock connection", run.id)
        notifier.send(
            Alert(
                Severity.WARNING,
                f"Extractor run {run.id} stopped",
                "It lost its database lock connection. The next run picks up its articles.",
            )
        )
        raise
    except Exception as exc:
        logger.exception("Extractor run %d failed", run.id)
        notifier.send(Alert(Severity.ERROR, f"Extractor run {run.id} failed", error_text(exc)))
        with engine.begin() as conn:
            finish_run(conn, run, "failed", error_text(exc))
        return "failed"

    status = "partial" if run.counts["failed"] else "succeeded"
    with engine.begin() as conn:
        finish_run(conn, run, status)
    logger.info("Extractor run %d %s: %s", run.id, status, run.counts)
    if status == "partial":
        every_article = run.counts["failed"] == run.counts["selected"]
        notifier.send(
            Alert(
                Severity.ERROR if every_article else Severity.WARNING,
                f"Extractor run {run.id} finished with failed articles",
                f"{run.counts['failed']} of {run.counts['selected']} articles failed. Their "
                "errors are in article_stages. Fix the cause, then re-run those articles.",
            )
        )
    return status


def run_extractor(
    engine: Engine,
    client: ModelClient,
    prompt: Prompt,
    notifier: Notifier,
    settings: ExtractorSettings,
    article_ids: Sequence[int] | None = None,
) -> RunResult | None:
    """Run the Extractor once. Returns None if another worker holds the lock.

    Without `article_ids`, the run takes graded articles with no current extraction, up to the
    setting's limit. With them, it extracts those articles again, including failed ones, adding
    new extractions beside the old.
    """
    if prompt.stage != STAGE:
        raise ValueError(f"The Extractor needs an {STAGE} prompt, not {prompt.name}")
    with agent_lock(engine, AGENT) as lock:
        if lock is None:
            logger.info("Another Extractor run holds the lock, so this one is exiting")
            return None

        with engine.begin() as conn:
            dead = find_running(conn, AGENT)
            if dead is not None:
                finish_run(conn, dead, "failed", "Interrupted. A later run took its articles.")
        if dead is not None:
            notifier.send(
                Alert(
                    Severity.WARNING,
                    f"Extractor run {dead.id} was interrupted",
                    "It was marked failed, and this run picks up the articles it didn't reach.",
                )
            )

        articles = select_articles(engine, settings.max_articles, article_ids)
        if article_ids is not None and len(articles) < len(article_ids):
            chosen = {a.id for a in articles}
            skipped = sorted(set(article_ids) - chosen)
            logger.warning("Skipping articles that aren't graded and in scope: %s", skipped)
        parameters = {
            "prompt": prompt.name,
            "prompt_version": prompt.version,
            "model": prompt.model,
            "source_basis": SOURCE_BASIS,
            "max_articles": settings.max_articles,
            "article_ids": sorted(article_ids) if article_ids is not None else None,
        }
        with engine.begin() as conn:
            run = start_run(conn, AGENT, parameters)
        logger.info("Starting Extractor run %d with %d articles", run.id, len(articles))
        status = _execute(engine, lock, client, prompt, notifier, run, articles)
        return RunResult(run.id, status)
