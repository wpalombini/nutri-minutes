"""Shared setup for Extractor tests: an abstract, a reply that passes its checks, graded articles
and an Extractor-shaped prompt."""

from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from pipeline.extractor.run import PROMPT_NAME
from pipeline.models.prompts import Prompt, load_prompt
from tests.grader_helpers import insert_in_scope
from tests.prompt_files import settings, write_prompt

TEMPLATE = """--- system ---
You extract facts.

--- user ---
Title: {{ title }}
Types: {{ publication_types }}
Design: {{ design }}
Main outcome: {{ main_outcome }}
Participants: {{ participants }}
Duration: {{ duration }}
Population: {{ population }}
Abstract: {{ abstract }}
{{ check_failure }}
"""

REPLY_SCHEMA: dict[str, Any] = load_prompt(PROMPT_NAME).reply_schema
"""The shipped prompt's schema, so tests run against the replies production accepts."""

ABSTRACT = (
    "We randomised 1,200 women aged 65 years or older to 800 IU of vitamin D a day or placebo "
    "for 3 years.\n\nHip fractures were less common with vitamin D (hazard ratio 0.80, 95% CI "
    "0.65 to 0.97). Bone density rose by 1.2% (p = 0.03). Falls occurred in 12 of 600 women "
    "taking vitamin D and 25 of 600 taking placebo. Adherence was self-reported."
)


def extractor_prompt(root: Path) -> Prompt:
    return write_prompt(
        root,
        "extractor/extract",
        TEMPLATE,
        settings(reply_schema=REPLY_SCHEMA, max_tokens=3000),
    )


def fact(kind: str, fact_text: str, quote: str) -> dict[str, Any]:
    return {"kind": kind, "fact": fact_text, "quote": quote}


def extracted(**overrides: Any) -> dict[str, Any]:
    """A reply for `ABSTRACT` with a hazard ratio and one fact of each kind."""
    reply: dict[str, Any] = {
        "population": "1,200 women aged 65 or older",
        "population_quote": "We randomised 1,200 women aged 65 years or older",
        "intervention": "800 IU of vitamin D a day for 3 years",
        "intervention_quote": "800 IU of vitamin D a day or placebo for 3 years",
        "comparator": "placebo",
        "comparator_quote": "800 IU of vitamin D a day or placebo",
        "measure": "hazard_ratio",
        "estimate": "0.80",
        "ci_lower": "0.65",
        "ci_upper": "0.97",
        "ci_level": "95",
        "unit": None,
        "outcome_label": "Hip fracture risk",
        "comparison_label": "Vitamin D compared with placebo",
        "lower_label": "Lower risk",
        "higher_label": "Higher risk",
        "effect_quote": "hazard ratio 0.80, 95% CI 0.65 to 0.97",
        "facts": [
            fact("outcome", "Hip fractures", "Hip fractures were less common with vitamin D"),
            fact(
                "result",
                "Bone density rose by 1.2% (p = 0.03).",
                "Bone density rose by 1.2% (p = 0.03).",
            ),
            fact(
                "absolute",
                "Falls: 12 of 600 with vitamin D, 25 of 600 with placebo.",
                "Falls occurred in 12 of 600 women taking vitamin D and 25 of 600 taking placebo.",
            ),
            fact("limitation", "Adherence was self-reported.", "Adherence was self-reported."),
        ],
    }
    reply.update(overrides)
    return reply


NO_EFFECT: dict[str, Any] = {
    "measure": "none",
    "estimate": None,
    "ci_lower": None,
    "ci_upper": None,
    "ci_level": None,
    "unit": None,
    "outcome_label": None,
    "comparison_label": None,
    "lower_label": None,
    "higher_label": None,
    "effect_quote": None,
}


def insert_graded(conn: Connection, number: int, gradable: bool = True, **overrides: Any) -> int:
    """An in-scope article with a grade (or a "not gradable" decision). Returns the article."""
    overrides.setdefault("abstract", ABSTRACT)
    article_id = insert_in_scope(conn, number, **overrides)
    add_grade(conn, article_id, gradable)
    return article_id


def add_grade(conn: Connection, article_id: int, gradable: bool = True) -> int:
    run_id = conn.execute(
        text(
            "INSERT INTO pipeline_runs (agent, status, parameters, finished_at) "
            "VALUES ('grader', 'succeeded', CAST('{}' AS jsonb), now()) RETURNING id"
        )
    ).scalar_one()
    if gradable:
        sql = (
            "INSERT INTO evidence_grades (article_id, run_id, decided_by, model_call_id, "
            "design_category, starting_level, level, main_outcome, participants, duration, "
            "population, funder_type, funding_source, funder_sells_product, sponsor_roles, "
            "registered, outcome_switched, surrogate_outcome, funding_lowered, reason) VALUES "
            "(:a, :r, 'model', :c, 'randomised_trial', 4, 4, 'hip fracture', 1200, '3 years', "
            "'women aged 65 or older', 'not_stated', 'not_stated', 'unknown', '{}', 'yes', "
            "'unknown', false, false, 'r') RETURNING id"
        )
    else:
        sql = (
            "INSERT INTO evidence_grades (article_id, run_id, decided_by, model_call_id, "
            "not_gradable, sponsor_roles, reason) VALUES "
            "(:a, :r, 'model', :c, 'narrative_review', '{}', 'r') RETURNING id"
        )
    call_id = conn.execute(
        text(
            "INSERT INTO model_calls (run_id, stage, prompt_name, prompt_version, attempt, "
            "input_values, model_requested, outcome, raw_reply, max_cost_usd, article_id) VALUES "
            "(:r, 'grader', 'grader/grade', 'v', 1, CAST('{}' AS jsonb), 'm', 'succeeded', "
            "'{}', 0, :a) RETURNING id"
        ),
        {"r": run_id, "a": article_id},
    ).scalar_one()
    return int(conn.execute(text(sql), {"a": article_id, "r": run_id, "c": call_id}).scalar_one())
