"""Model calls: one row per attempt by the model client (ADR 0005).

The `pipeline_worker` role can select and insert rows, but not change or delete them, so the
trace can't be rewritten.

Reversible: the downgrade drops the table, losing the trace.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_ROLE = "pipeline_worker"
OUTCOMES = "'succeeded', 'invalid_reply', 'error', 'refused'"


def upgrade() -> None:
    op.create_table(
        "model_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=True),
        sa.Column("prompt_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("input_values", postgresql.JSONB(), nullable=False),
        sa.Column("model_requested", sa.Text(), nullable=False),
        sa.Column("model_answered", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("generation_id", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("raw_reply", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(), nullable=True),
        sa.Column("max_cost_usd", sa.Numeric(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_model_calls"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_model_calls_run_id_pipeline_runs"
        ),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="fk_model_calls_article_id_articles"
        ),
        sa.CheckConstraint(f"outcome IN ({OUTCOMES})", name="ck_model_calls_outcome"),
        sa.CheckConstraint("attempt >= 1", name="ck_model_calls_attempt"),
        sa.CheckConstraint(
            "cost_usd >= 0 AND max_cost_usd >= 0", name="ck_model_calls_costs_not_negative"
        ),
        sa.CheckConstraint(
            "(outcome = 'succeeded') = (raw_reply IS NOT NULL AND error IS NULL)",
            name="ck_model_calls_succeeded_has_reply",
        ),
    )
    op.create_index("ix_model_calls_run_id_stage", "model_calls", ["run_id", "stage"])
    op.create_index("ix_model_calls_article_id", "model_calls", ["article_id"])
    op.execute(f"GRANT SELECT, INSERT ON model_calls TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("model_calls")
