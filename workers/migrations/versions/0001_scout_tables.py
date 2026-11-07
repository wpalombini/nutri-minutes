"""Scout tables: articles, licences, relations and pipeline runs.

Also creates the `pipeline_worker` group role if it doesn't exist. It can read and write these
tables but can't change the schema. Login roles for workers are created outside migrations and
granted membership.

Reversible: the downgrade drops the tables, losing their data. It keeps the role, because roles
belong to the whole server, and only revokes its access to this database.

Revision ID: 0001
Revises:
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_ROLE = "pipeline_worker"

LICENCE_CODES = (
    "'cc0', 'cc-by', 'cc-by-sa', 'cc-by-nc', 'cc-by-nd', "
    "'cc-by-nc-sa', 'cc-by-nc-nd', 'other', 'unknown'"
)
RELATION_TYPES = (
    "'retraction_in', 'retraction_of', 'erratum_in', 'erratum_for', "
    "'expression_of_concern_in', 'expression_of_concern_for', 'comment_in', 'comment_on', "
    "'update_in', 'update_of', 'republished_in', 'republished_from', 'other'"
)


def _id() -> sa.Column[int]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _timestamp(name: str) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "articles",
        _id(),
        sa.Column("doi", sa.Text(), nullable=True),
        sa.Column("pmid", sa.Text(), nullable=True),
        sa.Column("pmcid", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("authors", sa.Text(), nullable=True),
        sa.Column("journal", sa.Text(), nullable=True),
        sa.Column(
            "publication_types",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("first_indexed_on", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_record", postgresql.JSONB(), nullable=False),
        _timestamp("first_seen_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_articles"),
        sa.CheckConstraint(
            "num_nonnulls(doi, pmid, pmcid) >= 1", name="ck_articles_has_identifier"
        ),
        sa.CheckConstraint(
            r"doi ~ '^10\.[^[:space:]]+$' AND doi = lower(doi)", name="ck_articles_doi_format"
        ),
        sa.CheckConstraint("pmid ~ '^[1-9][0-9]*$'", name="ck_articles_pmid_format"),
        sa.CheckConstraint("pmcid ~ '^PMC[1-9][0-9]*$'", name="ck_articles_pmcid_format"),
    )
    op.create_index("ix_articles_doi", "articles", ["doi"], unique=True)
    op.create_index("ix_articles_pmid", "articles", ["pmid"], unique=True)
    op.create_index("ix_articles_pmcid", "articles", ["pmcid"], unique=True)

    op.create_table(
        "article_licences",
        _id(),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("licence_code", sa.Text(), nullable=False),
        sa.Column(
            "full_text_reuse_allowed",
            sa.Boolean(),
            sa.Computed("licence_code IN ('cc0', 'cc-by')", persisted=True),
            nullable=False,
        ),
        _timestamp("first_seen_at"),
        _timestamp("last_seen_at"),
        sa.PrimaryKeyConstraint("id", name="pk_article_licences"),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="fk_article_licences_article_id_articles"
        ),
        sa.CheckConstraint(
            f"licence_code IN ({LICENCE_CODES})", name="ck_article_licences_licence_code"
        ),
    )
    op.create_index(
        "ix_article_licences_article_id_source_last_seen_at_id",
        "article_licences",
        ["article_id", "source", "last_seen_at", "id"],
    )

    op.create_table(
        "article_relations",
        _id(),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("raw_type", sa.Text(), nullable=False),
        sa.Column("target_source", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("related_article_id", sa.BigInteger(), nullable=True),
        _timestamp("first_seen_at"),
        _timestamp("last_seen_at"),
        sa.PrimaryKeyConstraint("id", name="pk_article_relations"),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.id"], name="fk_article_relations_article_id_articles"
        ),
        sa.ForeignKeyConstraint(
            ["related_article_id"],
            ["articles.id"],
            name="fk_article_relations_related_article_id_articles",
        ),
        sa.CheckConstraint(
            f"relation_type IN ({RELATION_TYPES})", name="ck_article_relations_relation_type"
        ),
    )
    op.create_index(
        "uq_article_relations_article_id_target",
        "article_relations",
        ["article_id", "raw_type", "target_source", "target_id"],
        unique=True,
    )
    op.create_index(
        "ix_article_relations_related_article_id", "article_relations", ["related_article_id"]
    )
    op.create_index(
        "ix_article_relations_target_source_target_id",
        "article_relations",
        ["target_source", "target_id"],
    )

    op.create_table(
        "pipeline_runs",
        _id(),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=True),
        sa.Column(
            "counts", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("resume_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        _timestamp("started_at"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_runs"),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')",
            name="ck_pipeline_runs_status",
        ),
        sa.CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)", name="ck_pipeline_runs_finished_at"
        ),
        sa.CheckConstraint("resume_count >= 0", name="ck_pipeline_runs_resume_count"),
    )
    op.create_index(
        "uq_pipeline_runs_one_running_per_agent",
        "pipeline_runs",
        ["agent"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "ix_pipeline_runs_agent_status_started_at",
        "pipeline_runs",
        ["agent", "status", "started_at"],
    )

    op.create_table(
        "pipeline_run_errors",
        _id(),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("raw_record", postgresql.JSONB(), nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_run_errors"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], name="fk_pipeline_run_errors_run_id_pipeline_runs"
        ),
    )
    op.create_index("ix_pipeline_run_errors_run_id", "pipeline_run_errors", ["run_id"])

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{WORKER_ROLE}') THEN
                CREATE ROLE {WORKER_ROLE} NOLOGIN;
            END IF;
        END
        $$
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {WORKER_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON articles, article_licences, article_relations, "
        f"pipeline_runs TO {WORKER_ROLE}"
    )
    op.execute(f"GRANT SELECT, INSERT ON pipeline_run_errors TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("pipeline_run_errors")
    op.drop_table("pipeline_runs")
    op.drop_table("article_relations")
    op.drop_table("article_licences")
    op.drop_table("articles")
    # Roles belong to the whole server and may have access to other databases, so the role is
    # kept and only loses its access here.
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {WORKER_ROLE}")
