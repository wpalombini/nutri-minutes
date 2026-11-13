"""Extractor: structured facts for each graded article, each with the abstract text it came from.

`extractions` holds one row per extraction: who was studied, what was tested and against what,
and the main effect in the shape the study page's interval draws. `extraction_facts` holds the
rest: outcomes, other results, absolute numbers and the limits the authors state. Every fact keeps
the quote it came from. That a quote appears verbatim in the abstract, and that each number
appears in its quote, are the Extractor's checks, because they need the source text. The checks
here hold what one row can show, including an interval that is consistent with its estimate.

A re-run adds rows instead of changing them. The `pipeline_worker` role can only add rows.

Reversible: the downgrade drops both tables, losing the extractions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_ROLE = "pipeline_worker"

# Copied here rather than imported, so later changes to the models can't alter this revision.
RATIO_MEASURES = "('risk_ratio', 'odds_ratio', 'hazard_ratio', 'rate_ratio')"
MEASURES = (
    "('risk_ratio', 'odds_ratio', 'hazard_ratio', 'rate_ratio', "
    "'mean_difference', 'risk_difference', 'standardised_mean_difference')"
)
EFFECT_COLUMNS = (
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


def upgrade() -> None:
    op.create_table(
        "extractions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("grade_id", sa.BigInteger(), nullable=False),
        sa.Column("model_call_id", sa.BigInteger(), nullable=False),
        sa.Column("source_basis", sa.Text(), nullable=False),
        sa.Column("population", sa.Text(), nullable=False),
        sa.Column("population_quote", sa.Text(), nullable=False),
        sa.Column("intervention", sa.Text(), nullable=False),
        sa.Column("intervention_quote", sa.Text(), nullable=False),
        sa.Column("comparator", sa.Text(), nullable=True),
        sa.Column("comparator_quote", sa.Text(), nullable=True),
        sa.Column("measure", sa.Text(), nullable=True),
        sa.Column("estimate", sa.Numeric(), nullable=True),
        sa.Column("ci_lower", sa.Numeric(), nullable=True),
        sa.Column("ci_upper", sa.Numeric(), nullable=True),
        sa.Column("ci_level", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("outcome_label", sa.Text(), nullable=True),
        sa.Column("comparison_label", sa.Text(), nullable=True),
        sa.Column("lower_label", sa.Text(), nullable=True),
        sa.Column("higher_label", sa.Text(), nullable=True),
        sa.Column("effect_quote", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extractions"),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="fk_extractions_article_id_articles"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_extractions_run_id_pipeline_runs"
        ),
        sa.ForeignKeyConstraint(
            ["grade_id"], ["evidence_grades.id"], name="fk_extractions_grade_id_evidence_grades"
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["model_calls.id"], name="fk_extractions_model_call_id_model_calls"
        ),
        sa.CheckConstraint(
            "source_basis IN ('abstract', 'full_text')", name=op.f("ck_extractions_source_basis")
        ),
        # A null column makes its term null, which a check accepts: only empty text fails.
        sa.CheckConstraint(
            "length(population) > 0 AND length(population_quote) > 0 "
            "AND length(intervention) > 0 AND length(intervention_quote) > 0 "
            "AND length(comparator) > 0 AND length(comparator_quote) > 0 "
            "AND length(unit) > 0 AND length(outcome_label) > 0 "
            "AND length(comparison_label) > 0 AND length(lower_label) > 0 "
            "AND length(higher_label) > 0 AND length(effect_quote) > 0",
            name=op.f("ck_extractions_not_empty"),
        ),
        sa.CheckConstraint(
            "(comparator IS NULL) = (comparator_quote IS NULL)",
            name=op.f("ck_extractions_comparator_quote"),
        ),
        sa.CheckConstraint(
            f"measure IN {MEASURES}",
            name=op.f("ck_extractions_measure"),
        ),
        sa.CheckConstraint(
            "(measure IS NOT NULL AND estimate IS NOT NULL AND outcome_label IS NOT NULL "
            "AND comparison_label IS NOT NULL AND lower_label IS NOT NULL "
            "AND higher_label IS NOT NULL AND effect_quote IS NOT NULL) OR "
            f"(measure IS NULL AND num_nonnulls({', '.join(EFFECT_COLUMNS)}) = 0)",
            name=op.f("ck_extractions_effect_fields"),
        ),
        sa.CheckConstraint(
            "(ci_lower IS NULL AND ci_upper IS NULL AND ci_level IS NULL) OR "
            "(ci_lower IS NOT NULL AND ci_upper IS NOT NULL AND ci_level IS NOT NULL "
            "AND ci_lower < ci_upper AND ci_lower <= estimate AND estimate <= ci_upper)",
            name=op.f("ck_extractions_interval"),
        ),
        sa.CheckConstraint(
            "estimate NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND ci_lower NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND ci_upper NOT IN ('NaN', 'Infinity', '-Infinity')",
            name=op.f("ck_extractions_finite"),
        ),
        sa.CheckConstraint(
            "measure NOT IN ('mean_difference', 'risk_difference') OR unit IS NOT NULL",
            name=op.f("ck_extractions_difference_unit"),
        ),
        # A level as the study states it, such as 95 or 97.5; never rounded.
        sa.CheckConstraint(
            "ci_level >= 50 AND ci_level < 100", name=op.f("ck_extractions_ci_level")
        ),
        sa.CheckConstraint(
            f"NOT (measure IN {RATIO_MEASURES}) OR "
            "(estimate > 0 AND (ci_lower IS NULL OR ci_lower > 0) AND unit IS NULL)",
            name=op.f("ck_extractions_ratio"),
        ),
    )
    op.create_index("ix_extractions_article_id_id", "extractions", ["article_id", "id"])
    op.create_index("ix_extractions_grade_id", "extractions", ["grade_id"])
    op.create_index("ix_extractions_model_call_id", "extractions", ["model_call_id"])

    op.create_table(
        "extraction_facts",
        sa.Column("extraction_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("extraction_id", "position", name="pk_extraction_facts"),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["extractions.id"],
            name="fk_extraction_facts_extraction_id_extractions",
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_extraction_facts_position")),
        sa.CheckConstraint(
            "kind IN ('outcome', 'result', 'absolute', 'limitation')",
            name=op.f("ck_extraction_facts_kind"),
        ),
        sa.CheckConstraint(
            "length(fact) > 0 AND length(quote) > 0", name=op.f("ck_extraction_facts_not_empty")
        ),
    )
    op.execute(f"GRANT SELECT, INSERT ON extractions TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON extraction_facts TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("extraction_facts")
    op.drop_table("extractions")
