"""Triage runs: decide, one article at a time, whether new articles are in scope.

Rules drop clear cases first (`rules.py`). The model decides the rest. Every decision is stored
in `triage_decisions` with the article's `article_stages` row in one transaction, so an
interrupted run leaves no half-written article and a later run picks up what it didn't reach.
The rules every agent follows are in docs/agents.md.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, text

from pipeline.db.models import TOPIC_SLUGS
from pipeline.env import int_env
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
from pipeline.triage.rules import (
    RULES_VERSION,
    RuleDecision,
    TriageArticle,
    apply_rules,
    is_retracted_type,
)

logger = logging.getLogger(__name__)

AGENT = "triage"
STAGE = "triage"
"""The model client's budget stage. Its budget comes from `MODEL_BUDGET_USD_TRIAGE`."""
PROMPT_NAME = "triage/scope"
COUNT_KEYS = ("selected", "rule_out", "in_scope", "out_of_scope", "failed")
MAX_ERROR_LENGTH = 500


class ReplyError(ModelCallError):
    """The reply matched the schema but doesn't make sense, such as an unknown topic."""


@dataclass(frozen=True)
class TriageSettings:
    max_articles: int = 2000
    """The most articles one run looks at. The rest wait for the next run."""

    @classmethod
    def from_env(cls) -> TriageSettings:
        return cls(max_articles=int_env("TRIAGE_MAX_ARTICLES", 2000, 1))


@dataclass(frozen=True)
class ModelDecision:
    in_scope: bool
    relevance: int
    topics: tuple[str, ...]
    primary_topic: str | None
    reason: str


@dataclass(frozen=True)
class RunResult:
    run_id: int
    status: str


def prompt_inputs(article: TriageArticle) -> dict[str, str]:
    """The template's inputs. The prompt must use exactly these placeholders."""
    return {
        "title": article.title,
        "abstract": article.abstract or "",
        "publication_types": ", ".join(article.publication_types) or "not given",
    }


def parse_reply(reply: dict[str, Any]) -> ModelDecision:
    """Read the model's reply. The schema is checked by the client; this checks the meaning.

    An in-scope reply whose primary topic is missing from its topics gets it added, rather
    than losing the article over a slip. Out-of-scope decisions keep no topics.
    """
    in_scope, relevance, reason = reply.get("in_scope"), reply.get("relevance"), reply.get("reason")
    topics, primary = reply.get("topics"), reply.get("primary_topic")
    if not isinstance(in_scope, bool):
        raise ReplyError("Reply has no in_scope true or false")
    if type(relevance) is not int or not 1 <= relevance <= 5:
        raise ReplyError("Reply relevance isn't a whole number from 1 to 5")
    if not isinstance(reason, str) or not reason.strip():
        raise ReplyError("Reply has no reason")
    if not isinstance(topics, list) or not all(isinstance(t, str) for t in topics):
        raise ReplyError("Reply topics aren't a list of topics")
    if not isinstance(primary, str):
        raise ReplyError("Reply has no primary topic")
    if not in_scope:
        return ModelDecision(False, relevance, (), None, reason.strip())
    unknown = sorted(set(topics) - set(TOPIC_SLUGS))
    if unknown:
        raise ReplyError(f"Reply has unknown topics: {', '.join(unknown)}")
    if primary not in TOPIC_SLUGS:
        raise ReplyError("An in-scope reply needs a primary topic from the topic list")
    ordered = tuple(dict.fromkeys([primary, *topics]))
    return ModelDecision(True, relevance, ordered, primary, reason.strip())


SELECT_ARTICLES = """
SELECT a.id, a.title, a.abstract, a.language, a.publication_types,
       EXISTS (
           SELECT 1 FROM article_relations r
           WHERE (r.article_id = a.id AND r.relation_type = 'retraction_in')
              OR (r.related_article_id = a.id AND r.relation_type = 'retraction_of')
       ) AS retracted
FROM articles a
"""
PENDING_FILTER = (
    "WHERE NOT EXISTS (SELECT 1 FROM article_stages s "
    "WHERE s.article_id = a.id AND s.agent = :agent) ORDER BY a.id LIMIT :limit"
)
PENDING = text(SELECT_ARTICLES + PENDING_FILTER)
CHOSEN = text(SELECT_ARTICLES + "WHERE a.id = ANY(:ids) ORDER BY a.id")
UPSERT_STAGE = text(
    "INSERT INTO article_stages (article_id, agent, status, run_id, error) "
    "VALUES (:article_id, :agent, :status, :run_id, :error) "
    "ON CONFLICT (article_id, agent) DO UPDATE SET status = EXCLUDED.status, "
    "run_id = EXCLUDED.run_id, error = EXCLUDED.error, updated_at = now()"
)
INSERT_DECISION = text(
    "INSERT INTO triage_decisions (article_id, run_id, decided_by, rule, model_call_id, "
    "in_scope, relevance, topics, primary_topic, reason) VALUES (:article_id, :run_id, "
    ":decided_by, :rule, :model_call_id, :in_scope, :relevance, :topics, :primary_topic, :reason)"
)


def _article(row: Any) -> TriageArticle:
    types = tuple(row.publication_types)
    return TriageArticle(
        id=int(row.id),
        title=row.title,
        abstract=row.abstract,
        language=row.language,
        publication_types=types,
        retracted=bool(row.retracted) or is_retracted_type(types),
    )


def select_articles(
    engine: Engine, limit: int, article_ids: Sequence[int] | None = None
) -> list[TriageArticle]:
    """Articles Triage hasn't handled yet, oldest first, or the chosen ones for a re-run."""
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


def _store_rule(conn: Connection, run: Run, article: TriageArticle, decision: RuleDecision) -> None:
    conn.execute(
        INSERT_DECISION,
        {
            "article_id": article.id,
            "run_id": run.id,
            "decided_by": "rule",
            "rule": str(decision.rule),
            "model_call_id": None,
            "in_scope": False,
            "relevance": None,
            "topics": [],
            "primary_topic": None,
            "reason": decision.reason,
        },
    )
    _set_stage(conn, run, article.id, None)


def _store_model(
    conn: Connection, run: Run, article: TriageArticle, decision: ModelDecision, call_id: int
) -> None:
    conn.execute(
        INSERT_DECISION,
        {
            "article_id": article.id,
            "run_id": run.id,
            "decided_by": "model",
            "rule": None,
            "model_call_id": call_id,
            "in_scope": decision.in_scope,
            "relevance": decision.relevance,
            "topics": list(decision.topics),
            "primary_topic": decision.primary_topic,
            "reason": decision.reason,
        },
    )
    _set_stage(conn, run, article.id, None)


def _triage_one(
    engine: Engine,
    lock: AgentLock,
    client: ModelClient,
    prompt: Prompt,
    run: Run,
    article: TriageArticle,
) -> str:
    """Decide one article and store the result. Returns the count it adds to.

    `StopRun` propagates and leaves the article untouched, so the next run picks it up.
    """
    rule = apply_rules(article)
    model: ModelDecision | None = None
    call_id = 0
    failure: str | None = None
    if rule is None:
        try:
            result = client.call(CallRequest(run.id, prompt, prompt_inputs(article), article.id))
            model = parse_reply(result.reply)
            call_id = result.call_id
        except ModelCallError as exc:
            failure = str(exc)[:MAX_ERROR_LENGTH] or type(exc).__name__
            logger.warning("Triage run %d: article %d failed: %s", run.id, article.id, failure)

    if rule is not None:
        outcome = "rule_out"
    elif model is not None:
        outcome = "in_scope" if model.in_scope else "out_of_scope"
    else:
        outcome = "failed"
    counts = dict(run.counts)
    counts[outcome] += 1
    with engine.begin() as conn:
        if rule is not None:
            _store_rule(conn, run, article, rule)
        elif model is not None:
            _store_model(conn, run, article, model, call_id)
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
    articles: list[TriageArticle],
) -> str:
    for key in COUNT_KEYS:
        run.counts.setdefault(key, 0)
    run.counts["selected"] = len(articles)
    try:
        for article in articles:
            try:
                _triage_one(engine, lock, client, prompt, run, article)
            except StopRun, LockLost:
                raise
            except Exception as exc:
                # One bad article must not fail the run. If even marking it failed doesn't
                # work, the database is the problem and the run stops below.
                logger.exception("Triage run %d: article %d failed", run.id, article.id)
                _fail_article(engine, run, article.id, exc)
    except LockLost:
        logger.error("Triage run %d lost its lock connection", run.id)
        notifier.send(
            Alert(
                Severity.WARNING,
                f"Triage run {run.id} stopped",
                "It lost its database lock connection. The next run picks up its articles.",
            )
        )
        raise
    except Exception as exc:
        logger.exception("Triage run %d failed", run.id)
        notifier.send(Alert(Severity.ERROR, f"Triage run {run.id} failed", error_text(exc)))
        with engine.begin() as conn:
            finish_run(conn, run, "failed", error_text(exc))
        return "failed"

    status = "partial" if run.counts["failed"] else "succeeded"
    with engine.begin() as conn:
        finish_run(conn, run, status)
    logger.info("Triage run %d %s: %s", run.id, status, run.counts)
    if status == "partial":
        every_article = run.counts["failed"] == run.counts["selected"]
        notifier.send(
            Alert(
                Severity.ERROR if every_article else Severity.WARNING,
                f"Triage run {run.id} finished with failed articles",
                f"{run.counts['failed']} of {run.counts['selected']} articles failed. Their "
                "errors are in article_stages. Fix the cause, then re-run those articles.",
            )
        )
    return status


def run_triage(
    engine: Engine,
    client: ModelClient,
    prompt: Prompt,
    notifier: Notifier,
    settings: TriageSettings,
    article_ids: Sequence[int] | None = None,
) -> RunResult | None:
    """Run Triage once. Returns None if another worker holds the lock.

    Without `article_ids`, the run takes articles Triage hasn't handled, up to the setting's
    limit. With them, it decides those articles again, including failed ones, adding new
    decisions beside the old.
    """
    if prompt.stage != STAGE:
        raise ValueError(f"Triage needs a {STAGE} prompt, not {prompt.name}")
    with agent_lock(engine, AGENT) as lock:
        if lock is None:
            logger.info("Another Triage run holds the lock, so this one is exiting")
            return None

        # A dead run has nothing to resume: its finished articles are stored, and the rest have
        # no stage row, so this run takes them.
        with engine.begin() as conn:
            dead = find_running(conn, AGENT)
            if dead is not None:
                finish_run(conn, dead, "failed", "Interrupted. A later run took its articles.")
        if dead is not None:
            notifier.send(
                Alert(
                    Severity.WARNING,
                    f"Triage run {dead.id} was interrupted",
                    "It was marked failed, and this run picks up the articles it didn't reach.",
                )
            )

        articles = select_articles(engine, settings.max_articles, article_ids)
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
        logger.info("Starting Triage run %d with %d articles", run.id, len(articles))
        status = _execute(engine, lock, client, prompt, notifier, run, articles)
        return RunResult(run.id, status)
