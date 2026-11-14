"""Shared setup for Writer tests: extracted articles, a reply that passes its checks and a
Writer-shaped prompt."""

from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from pipeline.models.prompts import Prompt, load_prompt
from pipeline.writer.run import PROMPT_NAME
from tests.extractor_helpers import ABSTRACT, insert_graded
from tests.prompt_files import settings, write_prompt

TEMPLATE = """--- system ---
You write summaries.

--- user ---
Title: {{ title }}
Design: {{ design }}
Grade: {{ grade }}
Reasons: {{ grade_reasons }}
Funding: {{ funding }}
Effect: {{ main_effect }}
Facts: {{ facts }}
Fixed limit: {{ fixed_limit }}
Limits: {{ limit_count }}
Abstract: {{ abstract }}
{{ check_failure }}
"""

REPLY_SCHEMA: dict[str, Any] = load_prompt(PROMPT_NAME).reply_schema
"""The shipped prompt's schema, so tests run against the replies production accepts."""

PARAGRAPHS = [
    "This trial followed 1,200 women aged 65 or older for 3 years. Half took 800 IU of vitamin "
    "D each day, and the other half took a dummy pill. The researchers counted how many women "
    "broke a hip during that time. They also measured bone density and recorded falls in both "
    "groups.",
    "Fewer women broke a hip in the vitamin D group than in the placebo group. The range of "
    "likely results stayed below no difference, so the drop is unlikely to be chance alone. Bone "
    "density rose by 1.2% with vitamin D. Falls were less common too, with 12 of 600 women "
    "falling in the vitamin D group and 25 of 600 in the placebo group.",
    "The trial was randomised, which means chance decided who got vitamin D. That makes it more "
    "likely that the vitamin itself made the difference. Its grade is high certainty, the top of "
    "our scale. Still, the women reported for themselves whether they took their pills, so some "
    "may have missed doses without anyone knowing.",
]


def writer_prompt(root: Path) -> Prompt:
    return write_prompt(
        root, "writer/write", TEMPLATE, settings(reply_schema=REPLY_SCHEMA, max_tokens=2000)
    )


def written(**overrides: Any) -> dict[str, Any]:
    """A reply for the extraction `add_extraction` stores that passes every check."""
    reply: dict[str, Any] = {
        "headline": "Daily vitamin D cut hip fractures in older women over 3 years",
        "paragraphs": list(PARAGRAPHS),
        "limits": [
            "The women reported for themselves whether they took their pills.",
            "It only included older women, so it may not apply to men.",
        ],
        "result_sentence": "Fewer women broke a hip while taking vitamin D than while taking a "
        "dummy pill.",
        "absolute_sentence": "12 of 600 women fell while taking vitamin D, compared with 25 of 600 "
        "on the dummy pill.",
    }
    reply.update(overrides)
    return reply


def add_extraction(conn: Connection, article_id: int, effect: bool = True) -> int:
    """An extraction of `ABSTRACT` from the article's current grade, with one fact of each kind.
    Returns the extraction."""
    grade_id, run_id = conn.execute(
        text(
            "SELECT id, run_id FROM evidence_grades WHERE article_id = :a ORDER BY id DESC LIMIT 1"
        ),
        {"a": article_id},
    ).one()
    call_id = conn.execute(
        text(
            "INSERT INTO model_calls (run_id, stage, prompt_name, prompt_version, attempt, "
            "input_values, model_requested, outcome, raw_reply, max_cost_usd, article_id) VALUES "
            "(:r, 'extractor', 'extractor/extract', 'v', 1, CAST('{}' AS jsonb), 'm', "
            "'succeeded', '{}', 0, :a) RETURNING id"
        ),
        {"r": run_id, "a": article_id},
    ).scalar_one()
    values: dict[str, Any] = {
        "a": article_id,
        "r": run_id,
        "g": grade_id,
        "c": call_id,
        "measure": None,
        "estimate": None,
        "lower": None,
        "upper": None,
        "level": None,
        "outcome": None,
        "comparison": None,
        "low": None,
        "high": None,
        "quote": None,
    }
    if effect:
        values.update(
            measure="hazard_ratio",
            estimate="0.80",
            lower="0.65",
            upper="0.97",
            level="95",
            outcome="Hip fracture risk",
            comparison="Vitamin D compared with placebo",
            low="Lower risk",
            high="Higher risk",
            quote="hazard ratio 0.80, 95% CI 0.65 to 0.97",
        )
    extraction_id = conn.execute(
        text(
            "INSERT INTO extractions (article_id, run_id, grade_id, model_call_id, source_basis, "
            "population, population_quote, intervention, intervention_quote, comparator, "
            "comparator_quote, measure, estimate, ci_lower, ci_upper, ci_level, outcome_label, "
            "comparison_label, lower_label, higher_label, effect_quote) VALUES (:a, :r, :g, :c, "
            "'abstract', '1,200 women aged 65 or older', 'We randomised 1,200 women aged 65 "
            "years or older', '800 IU of vitamin D a day for 3 years', '800 IU of vitamin D a "
            "day or placebo for 3 years', 'placebo', '800 IU of vitamin D a day or placebo', "
            ":measure, CAST(:estimate AS numeric), CAST(:lower AS numeric), "
            "CAST(:upper AS numeric), CAST(:level AS numeric), :outcome, :comparison, :low, "
            ":high, :quote) RETURNING id"
        ),
        values,
    ).scalar_one()
    facts = [
        ("outcome", "Hip fractures", "Hip fractures were less common with vitamin D"),
        (
            "result",
            "Bone density rose by 1.2% (p = 0.03).",
            "Bone density rose by 1.2% (p = 0.03).",
        ),
        (
            "absolute",
            "Falls: 12 of 600 with vitamin D, 25 of 600 with placebo.",
            "Falls occurred in 12 of 600 women taking vitamin D and 25 of 600 taking placebo.",
        ),
        ("limitation", "Adherence was self-reported.", "Adherence was self-reported."),
    ]
    for position, (kind, fact, quote) in enumerate(facts, start=1):
        conn.execute(
            text(
                "INSERT INTO extraction_facts (extraction_id, position, kind, fact, quote) "
                "VALUES (:x, :p, :k, :f, :q)"
            ),
            {"x": extraction_id, "p": position, "k": kind, "f": fact, "q": quote},
        )
    return int(extraction_id)


def insert_extracted(conn: Connection, number: int, effect: bool = True, **overrides: Any) -> int:
    """An in-scope, graded and extracted article. Returns the article."""
    overrides.setdefault("abstract", ABSTRACT)
    article_id = insert_graded(conn, number, **overrides)
    add_extraction(conn, article_id, effect)
    return article_id


def add_licence(conn: Connection, article_id: int, code: str, source: str = "europe_pmc") -> None:
    conn.execute(
        text("INSERT INTO article_licences (article_id, source, licence_code) VALUES (:a, :s, :c)"),
        {"a": article_id, "s": source, "c": code},
    )
