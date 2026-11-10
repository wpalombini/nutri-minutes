"""Triage: each article's status per agent, and Triage's scope decisions.

`article_stages` is shared by every agent from Triage onwards. `triage_decisions` keeps every
decision, so a re-run adds a row instead of changing one. The `pipeline_worker` role can update
`article_stages`, because a person re-running an article changes its status, but can only add
decisions.

Reversible: the downgrade drops both tables, losing the decisions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_ROLE = "pipeline_worker"
# Copied here rather than imported, so later changes to the models can't alter this revision.
TOPICS = (
    "ARRAY['bone-health', 'muscle-and-strength', 'falls-and-independence', "
    "'heart-and-metabolism', 'brain-health', 'longevity', 'genes-and-diet']::text[]"
)


def upgrade() -> None:
    op.create_table(
        "article_stages",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("article_id", "agent", name="pk_article_stages"),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="fk_article_stages_article_id_articles"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_article_stages_run_id_pipeline_runs"
        ),
        sa.CheckConstraint("status IN ('done', 'failed')", name="ck_article_stages_status"),
        sa.CheckConstraint(
            "(status = 'failed') = (error IS NOT NULL)", name="ck_article_stages_failed_has_error"
        ),
    )
    op.create_index("ix_article_stages_agent_status", "article_stages", ["agent", "status"])

    op.create_table(
        "triage_decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("decided_by", sa.Text(), nullable=False),
        sa.Column("rule", sa.Text(), nullable=True),
        sa.Column("model_call_id", sa.BigInteger(), nullable=True),
        sa.Column("in_scope", sa.Boolean(), nullable=False),
        sa.Column("relevance", sa.Integer(), nullable=True),
        sa.Column(
            "topics",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("primary_topic", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_triage_decisions"),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="fk_triage_decisions_article_id_articles"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_triage_decisions_run_id_pipeline_runs"
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"],
            ["model_calls.id"],
            name="fk_triage_decisions_model_call_id_model_calls",
        ),
        sa.CheckConstraint(
            "decided_by IN ('rule', 'model')", name="ck_triage_decisions_decided_by"
        ),
        sa.CheckConstraint(
            "rule IN ('retracted', 'not_research', 'no_abstract', 'not_english')",
            name="ck_triage_decisions_rule",
        ),
        sa.CheckConstraint(
            "(decided_by = 'rule' AND rule IS NOT NULL AND model_call_id IS NULL "
            "AND relevance IS NULL AND NOT in_scope) OR "
            "(decided_by = 'model' AND rule IS NULL AND model_call_id IS NOT NULL "
            "AND relevance IS NOT NULL)",
            name="ck_triage_decisions_decider_fields",
        ),
        sa.CheckConstraint("relevance BETWEEN 1 AND 5", name="ck_triage_decisions_relevance"),
        sa.CheckConstraint(f"topics <@ {TOPICS}", name="ck_triage_decisions_topics"),
        sa.CheckConstraint(
            "(in_scope AND primary_topic IS NOT NULL AND primary_topic = ANY(topics)) OR "
            "(NOT in_scope AND primary_topic IS NULL AND cardinality(topics) = 0)",
            name="ck_triage_decisions_primary_topic",
        ),
    )
    op.create_index("ix_triage_decisions_article_id_id", "triage_decisions", ["article_id", "id"])
    op.create_index("ix_triage_decisions_model_call_id", "triage_decisions", ["model_call_id"])
    op.create_index(
        "ix_triage_decisions_topics", "triage_decisions", ["topics"], postgresql_using="gin"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON article_stages TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON triage_decisions TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("triage_decisions")
    op.drop_table("article_stages")
