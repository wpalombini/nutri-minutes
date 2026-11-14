"""Writer: plain-English summaries of each extracted article, one row per version.

`summaries` holds what the study page shows from the Writer: the headline, the body, and the
interval caption's result and absolute-numbers sentences. `summary_limits` holds the "What this
study does not show" items the Writer adds after the app's fixed first item. A summary is an
unchecked draft: the Fact-Checker and the Hype Detector record their results in their own tables,
and nothing publishes before both pass. That numbers come from the extraction, and that the reading
level and wording rules hold, needs the source and the extraction, so the Writer's code checks it.

A re-write adds a row instead of changing one. The `pipeline_worker` role can only add rows.

Reversible: the downgrade drops both tables, losing the summaries.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_ROLE = "pipeline_worker"


def upgrade() -> None:
    op.create_table(
        "summaries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("extraction_id", sa.BigInteger(), nullable=False),
        sa.Column("model_call_id", sa.BigInteger(), nullable=False),
        sa.Column("source_basis", sa.Text(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("result_sentence", sa.Text(), nullable=False),
        sa.Column("absolute_sentence", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_summaries"),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="fk_summaries_article_id_articles"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_summaries_run_id_pipeline_runs"
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"], ["extractions.id"], name="fk_summaries_extraction_id_extractions"
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["model_calls.id"], name="fk_summaries_model_call_id_model_calls"
        ),
        sa.CheckConstraint(
            "source_basis IN ('abstract', 'full_text')", name=op.f("ck_summaries_source_basis")
        ),
        # A null column makes its term null, which a check accepts: only empty text fails.
        sa.CheckConstraint(
            "length(headline) > 0 AND length(body) > 0 AND length(result_sentence) > 0 "
            "AND length(absolute_sentence) > 0",
            name=op.f("ck_summaries_not_empty"),
        ),
        # The headline and caption sentences are each shown as one line of text.
        sa.CheckConstraint(
            "headline !~ '[\\r\\n]' AND result_sentence !~ '[\\r\\n]' "
            "AND absolute_sentence !~ '[\\r\\n]'",
            name=op.f("ck_summaries_one_line"),
        ),
    )
    op.create_index("ix_summaries_article_id_id", "summaries", ["article_id", "id"])
    op.create_index("ix_summaries_extraction_id", "summaries", ["extraction_id"])
    op.create_index("ix_summaries_model_call_id", "summaries", ["model_call_id"])

    op.create_table(
        "summary_limits",
        sa.Column("summary_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("summary_id", "position", name="pk_summary_limits"),
        sa.ForeignKeyConstraint(
            ["summary_id"], ["summaries.id"], name="fk_summary_limits_summary_id_summaries"
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_summary_limits_position")),
        sa.CheckConstraint(
            "length(statement) > 0 AND statement !~ '[\\r\\n]'",
            name=op.f("ck_summary_limits_statement"),
        ),
    )
    op.execute(f"GRANT SELECT, INSERT ON summaries TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON summary_limits TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("summary_limits")
    op.drop_table("summaries")
