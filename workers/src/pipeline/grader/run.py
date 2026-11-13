"""Evidence Grader runs: grade, one article at a time, the articles Triage kept.

Rules mark clear non-studies first (`rules.py`). The model reads the rest, and `grading.py` turns
its reading into a grade. Each grade, its reasons and the article's `article_stages` row are
stored in one transaction, so an interrupted run leaves no half-written article and a later run
picks up what it didn't reach. The rules every agent follows are in docs/agents.md.

The run loop follows Triage's (`pipeline.triage.run`) on purpose; the two can share it once a
third agent shows what the common part is.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Engine, text

from pipeline.env import int_env
from pipeline.grader.grading import Grade, NotGradable, ReplyError, parse_reply
from pipeline.grader.rules import (
    RULES_VERSION,
    GraderArticle,
    RuleDecision,
    apply_rules,
    design_conflict,
)
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

AGENT = "grader"
STAGE = "grader"
"""The model client's budget stage. Its budget comes from `MODEL_BUDGET_USD_GRADER`."""
PROMPT_NAME = "grader/grade"
DEFAULT_BUDGET_USD = Decimal("1.00")
"""Per run, unless `MODEL_BUDGET_USD_GRADER` sets another. A full run of 300 articles costs about
US$0.25 on Haiku 5.5 (US$0.05 for the 69 eval papers), so this leaves room for retries. A spent
budget stops the run, and the rest wait for the next."""
COUNT_KEYS = ("selected", "rule_not_gradable", "not_gradable", "graded", "failed")
MAX_ERROR_LENGTH = 500
REPLY_ATTEMPTS = 3
"""Calls per article when replies match the schema but make no sense. The client retries other
failures itself."""
MAX_GRANT_AGENCIES = 10


@dataclass(frozen=True)
class GraderSettings:
    max_articles: int = 300
    """The most articles one run looks at. The rest wait for the next run."""

    @classmethod
    def from_env(cls) -> GraderSettings:
        return cls(max_articles=int_env("GRADER_MAX_ARTICLES", 300, 1))


@dataclass(frozen=True)
class RunResult:
    run_id: int
    status: str


def prompt_inputs(article: GraderArticle) -> dict[str, str]:
    """The template's inputs. The prompt must use exactly these placeholders."""
    return {
        "title": article.title,
        "abstract": article.abstract or "",
        "publication_types": ", ".join(article.publication_types) or "not given",
        "grant_agencies": "; ".join(article.grant_agencies) or "none listed",
    }


def grant_agencies(grants: Any) -> tuple[str, ...]:
    """Funder names from a Europe PMC `grantsList`, deduplicated, at most `MAX_GRANT_AGENCIES`."""
    if not isinstance(grants, dict) or not isinstance(grants.get("grant"), list):
        return ()
    names = [
        g["agency"].strip()
        for g in grants["grant"]
        if isinstance(g, dict) and isinstance(g.get("agency"), str) and g["agency"].strip()
    ]
    return tuple(dict.fromkeys(names))[:MAX_GRANT_AGENCIES]


SELECT_ARTICLES = """
SELECT a.id, a.title, a.abstract, a.publication_types, a.source_record -> 'grantsList' AS grants
FROM articles a
JOIN LATERAL (
    SELECT d.in_scope FROM triage_decisions d WHERE d.article_id = a.id ORDER BY d.id DESC LIMIT 1
) latest ON latest.in_scope
"""
PENDING = text(
    SELECT_ARTICLES  # noqa: S608 (fixed text)
    + "WHERE NOT EXISTS (SELECT 1 FROM article_stages s "
    "WHERE s.article_id = a.id AND s.agent = :agent) ORDER BY a.id LIMIT :limit"
)
CHOSEN = text(SELECT_ARTICLES + "WHERE a.id = ANY(:ids) ORDER BY a.id")
UPSERT_STAGE = text(
    "INSERT INTO article_stages (article_id, agent, status, run_id, error) "
    "VALUES (:article_id, :agent, :status, :run_id, :error) "
    "ON CONFLICT (article_id, agent) DO UPDATE SET status = EXCLUDED.status, "
    "run_id = EXCLUDED.run_id, error = EXCLUDED.error, updated_at = now()"
)
GRADE_COLUMNS = (
    "article_id",
    "run_id",
    "decided_by",
    "model_call_id",
    "not_gradable",
    "design_category",
    "review_includes",
    "review_reported_level",
    "starting_level",
    "level",
    "main_outcome",
    "participants",
    "duration",
    "population",
    "funder",
    "funder_type",
    "funding_source",
    "funder_sells_product",
    "sponsor_roles",
    "conflicts",
    "registered",
    "outcome_switched",
    "surrogate_outcome",
    "funding_lowered",
    "reason",
)
INSERT_GRADE = text(
    f"INSERT INTO evidence_grades ({', '.join(GRADE_COLUMNS)}) "  # noqa: S608 (fixed names)
    f"VALUES ({', '.join(':' + c for c in GRADE_COLUMNS)}) RETURNING id"
)
INSERT_REASON = text(
    "INSERT INTO evidence_grade_reasons (grade_id, position, factor, direction, levels, reason) "
    "VALUES (:grade_id, :position, :factor, :direction, :levels, :reason)"
)


def _article(row: Any) -> GraderArticle:
    return GraderArticle(
        id=int(row.id),
        title=row.title,
        abstract=row.abstract,
        publication_types=tuple(row.publication_types),
        grant_agencies=grant_agencies(row.grants),
    )


def select_articles(
    engine: Engine, limit: int, article_ids: Sequence[int] | None = None
) -> list[GraderArticle]:
    """In-scope articles the Grader hasn't handled yet, oldest first, or the chosen ones for a
    re-run. Chosen articles whose latest Triage decision is out of scope are left out."""
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


def _empty_row(run: Run, article: GraderArticle) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(GRADE_COLUMNS)
    row.update(article_id=article.id, run_id=run.id, sponsor_roles=[])
    return row


def _store_not_gradable(
    conn: Connection,
    run: Run,
    article: GraderArticle,
    decision: RuleDecision | NotGradable,
    call_id: int | None,
) -> None:
    row = _empty_row(run, article)
    row.update(
        decided_by="model" if call_id is not None else "rule",
        model_call_id=call_id,
        not_gradable=decision.not_gradable,
        reason=decision.reason,
    )
    conn.execute(INSERT_GRADE, row)
    _set_stage(conn, run, article.id, None)


def _store_grade(
    conn: Connection, run: Run, article: GraderArticle, grade: Grade, call_id: int
) -> None:
    funding = grade.funding
    row = _empty_row(run, article)
    row.update(
        decided_by="model",
        model_call_id=call_id,
        design_category=grade.design_category,
        review_includes=grade.review_includes,
        review_reported_level=grade.review_reported_level,
        starting_level=grade.starting_level,
        level=grade.level,
        main_outcome=grade.main_outcome,
        participants=grade.participants,
        duration=grade.duration,
        population=grade.population,
        funder=funding.funder,
        funder_type=funding.funder_type,
        funding_source=funding.funding_source,
        funder_sells_product=funding.funder_sells_product,
        sponsor_roles=list(funding.sponsor_roles),
        conflicts=funding.conflicts,
        registered=funding.registered,
        outcome_switched=funding.outcome_switched,
        surrogate_outcome=funding.surrogate_outcome,
        funding_lowered=grade.funding_lowered,
        reason=grade.reason,
    )
    grade_id = conn.execute(INSERT_GRADE, row).scalar_one()
    for position, reason in enumerate(grade.reasons, start=1):
        conn.execute(
            INSERT_REASON,
            {
                "grade_id": grade_id,
                "position": position,
                "factor": reason.factor,
                "direction": reason.direction,
                "levels": reason.levels,
                "reason": reason.text,
            },
        )
    _set_stage(conn, run, article.id, None)


def _read(article: GraderArticle, reply: dict[str, Any]) -> Grade | NotGradable:
    decision = parse_reply(reply)
    if isinstance(decision, Grade):
        conflict = design_conflict(article, decision.design_category)
        if conflict is not None:
            raise ReplyError(conflict)
        if decision.funding.funding_source == "grant_metadata" and not article.grant_agencies:
            raise ReplyError("Funding comes from the grant list, but none is listed")
    return decision


def ask_model(
    client: ModelClient, article: GraderArticle, request: CallRequest
) -> tuple[Grade | NotGradable, int]:
    """Ask the model, calling again when a reply makes no sense. Returns the decision and the
    call it came from. Used by runs and the eval alike."""
    for _ in range(REPLY_ATTEMPTS - 1):
        result = client.call(request)
        try:
            return _read(article, result.reply), result.call_id
        except ReplyError as exc:
            logger.info(
                "Grader run %d: asking again after call %d: %s", request.run_id, result.call_id, exc
            )
    result = client.call(request)
    return _read(article, result.reply), result.call_id


def _grade_one(
    engine: Engine,
    lock: AgentLock,
    client: ModelClient,
    prompt: Prompt,
    run: Run,
    article: GraderArticle,
) -> str:
    """Grade one article and store the result. Returns the count it adds to.

    `StopRun` propagates and leaves the article untouched, so the next run picks it up.
    """
    rule = apply_rules(article)
    decision: Grade | NotGradable | None = None
    call_id = 0
    failure: str | None = None
    if rule is None:
        if not (article.abstract or "").strip():
            failure = "No abstract to grade from"
        else:
            try:
                decision, call_id = ask_model(
                    client, article, CallRequest(run.id, prompt, prompt_inputs(article), article.id)
                )
            except ModelCallError as exc:
                failure = str(exc)[:MAX_ERROR_LENGTH] or type(exc).__name__
        if failure is not None:
            logger.warning("Grader run %d: article %d failed: %s", run.id, article.id, failure)

    if rule is not None:
        outcome = "rule_not_gradable"
    elif isinstance(decision, Grade):
        outcome = "graded"
    elif isinstance(decision, NotGradable):
        outcome = "not_gradable"
    else:
        outcome = "failed"
    counts = dict(run.counts)
    counts[outcome] += 1
    with engine.begin() as conn:
        if rule is not None:
            _store_not_gradable(conn, run, article, rule, None)
        elif isinstance(decision, Grade):
            _store_grade(conn, run, article, decision, call_id)
        elif isinstance(decision, NotGradable):
            _store_not_gradable(conn, run, article, decision, call_id)
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
    articles: list[GraderArticle],
) -> str:
    for key in COUNT_KEYS:
        run.counts.setdefault(key, 0)
    run.counts["selected"] = len(articles)
    try:
        for article in articles:
            try:
                _grade_one(engine, lock, client, prompt, run, article)
            except StopRun, LockLost:
                raise
            except Exception as exc:
                # One bad article must not fail the run. If even marking it failed doesn't
                # work, the database is the problem and the run stops below.
                logger.exception("Grader run %d: article %d failed", run.id, article.id)
                _fail_article(engine, run, article.id, exc)
    except LockLost:
        logger.error("Grader run %d lost its lock connection", run.id)
        notifier.send(
            Alert(
                Severity.WARNING,
                f"Grader run {run.id} stopped",
                "It lost its database lock connection. The next run picks up its articles.",
            )
        )
        raise
    except Exception as exc:
        logger.exception("Grader run %d failed", run.id)
        notifier.send(Alert(Severity.ERROR, f"Grader run {run.id} failed", error_text(exc)))
        with engine.begin() as conn:
            finish_run(conn, run, "failed", error_text(exc))
        return "failed"

    status = "partial" if run.counts["failed"] else "succeeded"
    with engine.begin() as conn:
        finish_run(conn, run, status)
    logger.info("Grader run %d %s: %s", run.id, status, run.counts)
    if status == "partial":
        every_article = run.counts["failed"] == run.counts["selected"]
        notifier.send(
            Alert(
                Severity.ERROR if every_article else Severity.WARNING,
                f"Grader run {run.id} finished with failed articles",
                f"{run.counts['failed']} of {run.counts['selected']} articles failed. Their "
                "errors are in article_stages. Fix the cause, then re-run those articles.",
            )
        )
    return status


def run_grader(
    engine: Engine,
    client: ModelClient,
    prompt: Prompt,
    notifier: Notifier,
    settings: GraderSettings,
    article_ids: Sequence[int] | None = None,
) -> RunResult | None:
    """Run the Grader once. Returns None if another worker holds the lock.

    Without `article_ids`, the run takes in-scope articles the Grader hasn't handled, up to the
    setting's limit. With them, it grades those articles again, including failed ones, adding
    new grades beside the old.
    """
    if prompt.stage != STAGE:
        raise ValueError(f"The Grader needs a {STAGE} prompt, not {prompt.name}")
    with agent_lock(engine, AGENT) as lock:
        if lock is None:
            logger.info("Another Grader run holds the lock, so this one is exiting")
            return None

        with engine.begin() as conn:
            dead = find_running(conn, AGENT)
            if dead is not None:
                finish_run(conn, dead, "failed", "Interrupted. A later run took its articles.")
        if dead is not None:
            notifier.send(
                Alert(
                    Severity.WARNING,
                    f"Grader run {dead.id} was interrupted",
                    "It was marked failed, and this run picks up the articles it didn't reach.",
                )
            )

        articles = select_articles(engine, settings.max_articles, article_ids)
        if article_ids is not None and len(articles) < len(article_ids):
            chosen = {a.id for a in articles}
            skipped = sorted(set(article_ids) - chosen)
            logger.warning("Skipping articles that aren't in scope or don't exist: %s", skipped)
        parameters = {
            "prompt": prompt.name,
            "prompt_version": prompt.version,
            "model": prompt.model,
            "rules_version": RULES_VERSION,
            "max_articles": settings.max_articles,
            "article_ids": sorted(article_ids) if article_ids is not None else None,
        }
        with engine.begin() as conn:
            run = start_run(conn, AGENT, parameters)
        logger.info("Starting Grader run %d with %d articles", run.id, len(articles))
        status = _execute(engine, lock, client, prompt, notifier, run, articles)
        return RunResult(run.id, status)
