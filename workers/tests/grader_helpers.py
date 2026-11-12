"""Shared setup for Grader tests: replies, in-scope articles and a Grader-shaped prompt."""

from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from pipeline.grader.run import PROMPT_NAME
from pipeline.models.prompts import Prompt, load_prompt
from tests.prompt_files import settings, write_prompt
from tests.triage_helpers import insert_article

TEMPLATE = """--- system ---
You grade papers.

--- user ---
Title: {{ title }}
Types: {{ publication_types }}
Funders: {{ grant_agencies }}
Abstract: {{ abstract }}
"""

REPLY_SCHEMA: dict[str, Any] = load_prompt(PROMPT_NAME).reply_schema
"""The shipped prompt's schema, so tests run against the replies production accepts."""


def grader_prompt(root: Path) -> Prompt:
    return write_prompt(
        root, "grader/grade", TEMPLATE, settings(reply_schema=REPLY_SCHEMA, max_tokens=1500)
    )


def move(
    factor: str, direction: str = "lowers", levels: int = 1, text: str = "x"
) -> dict[str, Any]:
    return {"factor": factor, "direction": direction, "levels": levels, "text": text}


def graded(**overrides: Any) -> dict[str, Any]:
    """A reply for a randomised trial with one move down for size and no funding concern."""
    reply: dict[str, Any] = {
        "reason": "Small randomised trial.",
        "gradable": True,
        "not_gradable": "none",
        "design_category": "randomised_trial",
        "review_includes": "none",
        "review_reported_level": None,
        "main_outcome": "hip bone density",
        "participants": 60,
        "duration": "12 months",
        "population": "women aged 60 to 75",
        "moves": [move("size", text="60 women.")],
        "funder": "A national research council",
        "funder_type": "public",
        "funding_source": "abstract",
        "funder_sells_product": "no",
        "sponsor_roles": [],
        "conflicts": None,
        "registered": "yes",
        "outcome_switched": "unknown",
        "surrogate_outcome": False,
        "funding_risks_counted_elsewhere": False,
        "funding_concern": None,
    }
    reply.update(overrides)
    return reply


def not_gradable(kind: str = "narrative_review") -> dict[str, Any]:
    return graded(
        reason="An overview without a systematic search.",
        gradable=False,
        not_gradable=kind,
        design_category="none",
        moves=[],
    )


def insert_in_scope(conn: Connection, number: int, in_scope: bool = True, **overrides: Any) -> int:
    """An article with a Triage decision, in scope by default."""
    article_id = insert_article(conn, number, **overrides)
    run_id = conn.execute(
        text(
            "INSERT INTO pipeline_runs (agent, status, parameters, finished_at) "
            "VALUES ('triage', 'succeeded', CAST('{}' AS jsonb), now()) RETURNING id"
        )
    ).scalar_one()
    if in_scope:
        conn.execute(
            text(
                "INSERT INTO triage_decisions (article_id, run_id, decided_by, model_call_id, "
                "in_scope, relevance, topics, primary_topic, reason) VALUES (:a, :r, 'model', "
                ":c, true, 4, '{bone-health}', 'bone-health', 'r')"
            ),
            {"a": article_id, "r": run_id, "c": _call(conn, run_id)},
        )
    else:
        conn.execute(
            text(
                "INSERT INTO triage_decisions (article_id, run_id, decided_by, rule, in_scope, "
                "reason) VALUES (:a, :r, 'rule', 'no_abstract', false, 'r')"
            ),
            {"a": article_id, "r": run_id},
        )
    return article_id


def _call(conn: Connection, run_id: int) -> int:
    return int(
        conn.execute(
            text(
                "INSERT INTO model_calls (run_id, stage, prompt_name, prompt_version, attempt, "
                "input_values, model_requested, outcome, raw_reply, max_cost_usd) VALUES "
                "(:r, 'triage', 'triage/scope', 'v', 1, CAST('{}' AS jsonb), 'm', "
                "'succeeded', '{}', 0) RETURNING id"
            ),
            {"r": run_id},
        ).scalar_one()
    )
