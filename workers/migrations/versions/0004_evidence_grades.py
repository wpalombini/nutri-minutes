"""Evidence Grader: grades for each article's main outcome, and the reasons they moved.

`evidence_grades` keeps every grade, so a re-run adds a row instead of changing one. The checks
hold what one row can show: starting levels by design, the caps on moving up, and which fields a
graded or ungraded paper has. That the level equals the starting level plus the reasons' moves is
the Grader's job, because it spans two tables. The `pipeline_worker` role can only add rows.

Reversible: the downgrade drops both tables, losing the grades.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_ROLE = "pipeline_worker"

# Copied here rather than imported, so later changes to the models can't alter this revision.
STARTING_LEVEL = (
    "CASE design_category "
    "WHEN 'randomised_trial' THEN starting_level = 4 "
    "WHEN 'non_randomised_trial' THEN starting_level = 2 "
    "WHEN 'observational' THEN starting_level = 2 "
    "WHEN 'animal' THEN starting_level = 1 "
    "WHEN 'lab' THEN starting_level = 1 "
    "WHEN 'review' THEN starting_level = COALESCE(review_reported_level, "
    "CASE review_includes WHEN 'randomised_trials' THEN 4 WHEN 'observational' THEN 2 "
    "WHEN 'mixed' THEN 2 WHEN 'animal_or_lab' THEN 1 END) "
    "END"
)
YES_NO_UNKNOWN = "('yes', 'no', 'unknown')"
FUNDING_LOWERED = (
    "NOT funding_lowered OR "
    "(funder_sells_product = 'yes' AND sponsor_roles && ARRAY['analysis', 'writing']::text[]) "
    "OR outcome_switched = 'yes' OR registered = 'no' OR surrogate_outcome"
)


def upgrade() -> None:
    op.create_table(
        "evidence_grades",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("decided_by", sa.Text(), nullable=False),
        sa.Column("model_call_id", sa.BigInteger(), nullable=True),
        sa.Column("not_gradable", sa.Text(), nullable=True),
        sa.Column("design_category", sa.Text(), nullable=True),
        sa.Column("review_includes", sa.Text(), nullable=True),
        sa.Column("review_reported_level", sa.SmallInteger(), nullable=True),
        sa.Column("starting_level", sa.SmallInteger(), nullable=True),
        sa.Column("level", sa.SmallInteger(), nullable=True),
        sa.Column("main_outcome", sa.Text(), nullable=True),
        sa.Column("participants", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Text(), nullable=True),
        sa.Column("population", sa.Text(), nullable=True),
        sa.Column("funder", sa.Text(), nullable=True),
        sa.Column("funder_type", sa.Text(), nullable=True),
        sa.Column("funding_source", sa.Text(), nullable=True),
        sa.Column("funder_sells_product", sa.Text(), nullable=True),
        sa.Column(
            "sponsor_roles",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("conflicts", sa.Text(), nullable=True),
        sa.Column("registered", sa.Text(), nullable=True),
        sa.Column("outcome_switched", sa.Text(), nullable=True),
        sa.Column("surrogate_outcome", sa.Boolean(), nullable=True),
        sa.Column("funding_lowered", sa.Boolean(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_grades"),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="fk_evidence_grades_article_id_articles"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_evidence_grades_run_id_pipeline_runs"
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"],
            ["model_calls.id"],
            name="fk_evidence_grades_model_call_id_model_calls",
        ),
        sa.CheckConstraint(
            "decided_by IN ('rule', 'model')", name=op.f("ck_evidence_grades_decided_by")
        ),
        sa.CheckConstraint(
            "(decided_by = 'rule' AND model_call_id IS NULL AND not_gradable IS NOT NULL) OR "
            "(decided_by = 'model' AND model_call_id IS NOT NULL)",
            name=op.f("ck_evidence_grades_decider_fields"),
        ),
        sa.CheckConstraint(
            "not_gradable IN ('narrative_review', 'case_report', 'protocol', 'not_a_study')",
            name=op.f("ck_evidence_grades_not_gradable"),
        ),
        sa.CheckConstraint(
            "design_category IN ('randomised_trial', 'non_randomised_trial', 'observational', "
            "'review', 'animal', 'lab')",
            name=op.f("ck_evidence_grades_design_category"),
        ),
        sa.CheckConstraint(
            "review_includes IN ('randomised_trials', 'observational', 'mixed', 'animal_or_lab')",
            name=op.f("ck_evidence_grades_review_includes"),
        ),
        sa.CheckConstraint(
            "funder_type IN ('industry', 'public', 'charity', 'none', 'not_stated')",
            name=op.f("ck_evidence_grades_funder_type"),
        ),
        sa.CheckConstraint(
            "funding_source IN ('abstract', 'grant_metadata', 'full_text', 'not_stated')",
            name=op.f("ck_evidence_grades_funding_source"),
        ),
        sa.CheckConstraint(
            f"funder_sells_product IN {YES_NO_UNKNOWN}",
            name=op.f("ck_evidence_grades_funder_sells_product"),
        ),
        sa.CheckConstraint(
            f"registered IN {YES_NO_UNKNOWN}", name=op.f("ck_evidence_grades_registered")
        ),
        sa.CheckConstraint(
            f"outcome_switched IN {YES_NO_UNKNOWN}",
            name=op.f("ck_evidence_grades_outcome_switched"),
        ),
        sa.CheckConstraint(
            "sponsor_roles <@ ARRAY['design', 'analysis', 'writing']::text[]",
            name=op.f("ck_evidence_grades_sponsor_roles"),
        ),
        sa.CheckConstraint(
            "(not_gradable IS NULL AND design_category IS NOT NULL "
            "AND starting_level IS NOT NULL AND level IS NOT NULL AND main_outcome IS NOT NULL "
            "AND funder_type IS NOT NULL AND funding_source IS NOT NULL "
            "AND funder_sells_product IS NOT NULL AND registered IS NOT NULL "
            "AND outcome_switched IS NOT NULL AND surrogate_outcome IS NOT NULL "
            "AND funding_lowered IS NOT NULL) OR "
            "(not_gradable IS NOT NULL AND design_category IS NULL AND starting_level IS NULL "
            "AND level IS NULL AND main_outcome IS NULL AND participants IS NULL "
            "AND duration IS NULL AND population IS NULL AND funder IS NULL "
            "AND funder_type IS NULL AND funding_source IS NULL "
            "AND funder_sells_product IS NULL AND cardinality(sponsor_roles) = 0 "
            "AND conflicts IS NULL AND registered IS NULL AND outcome_switched IS NULL "
            "AND surrogate_outcome IS NULL AND funding_lowered IS NULL)",
            name=op.f("ck_evidence_grades_graded_fields"),
        ),
        sa.CheckConstraint(
            "(design_category = 'review' AND review_includes IS NOT NULL) OR "
            "(design_category IS DISTINCT FROM 'review' AND review_includes IS NULL "
            "AND review_reported_level IS NULL)",
            name=op.f("ck_evidence_grades_review_fields"),
        ),
        sa.CheckConstraint(
            "review_reported_level BETWEEN 1 AND 4",
            name=op.f("ck_evidence_grades_review_reported_level"),
        ),
        sa.CheckConstraint(STARTING_LEVEL, name=op.f("ck_evidence_grades_starting_level")),
        sa.CheckConstraint(
            "level BETWEEN 1 AND 4 AND level <= starting_level + 1 AND "
            "(level <= starting_level OR (design_category NOT IN ('animal', 'lab') "
            "AND review_includes IS DISTINCT FROM 'animal_or_lab'))",
            name=op.f("ck_evidence_grades_level"),
        ),
        sa.CheckConstraint("participants > 0", name=op.f("ck_evidence_grades_participants")),
        sa.CheckConstraint(
            "(funding_source = 'not_stated') = (funder_type = 'not_stated')",
            name=op.f("ck_evidence_grades_funding_not_stated"),
        ),
        sa.CheckConstraint(FUNDING_LOWERED, name=op.f("ck_evidence_grades_funding_lowered")),
        sa.CheckConstraint(
            "length(main_outcome) > 0 AND length(reason) > 0",
            name=op.f("ck_evidence_grades_not_empty"),
        ),
    )
    op.create_index("ix_evidence_grades_article_id_id", "evidence_grades", ["article_id", "id"])
    op.create_index("ix_evidence_grades_model_call_id", "evidence_grades", ["model_call_id"])

    op.create_table(
        "evidence_grade_reasons",
        sa.Column("grade_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("factor", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("levels", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("grade_id", "position", name="pk_evidence_grade_reasons"),
        sa.ForeignKeyConstraint(
            ["grade_id"],
            ["evidence_grades.id"],
            name="fk_evidence_grade_reasons_grade_id_evidence_grades",
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_evidence_grade_reasons_position")),
        sa.CheckConstraint(
            "factor IN ('design', 'size', 'duration', 'population', 'funding_and_conflicts')",
            name=op.f("ck_evidence_grade_reasons_factor"),
        ),
        sa.CheckConstraint(
            "direction IN ('raises', 'lowers')", name=op.f("ck_evidence_grade_reasons_direction")
        ),
        sa.CheckConstraint("levels BETWEEN 0 AND 2", name=op.f("ck_evidence_grade_reasons_levels")),
        sa.CheckConstraint("length(reason) > 0", name=op.f("ck_evidence_grade_reasons_reason")),
        sa.CheckConstraint(
            "factor <> 'funding_and_conflicts' OR (direction = 'lowers' AND levels <= 1)",
            name=op.f("ck_evidence_grade_reasons_funding"),
        ),
    )
    op.create_index(
        "uq_evidence_grade_reasons_one_funding_drop",
        "evidence_grade_reasons",
        ["grade_id"],
        unique=True,
        postgresql_where=sa.text("factor = 'funding_and_conflicts' AND levels > 0"),
    )
    op.execute(f"GRANT SELECT, INSERT ON evidence_grades TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON evidence_grade_reasons TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("evidence_grade_reasons")
    op.drop_table("evidence_grades")
