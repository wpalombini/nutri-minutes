"""SQLAlchemy models for the tables described in docs/database.md.

Alembic migrations are the source of truth for the schema. These models must match them, and
`alembic check` in CI fails when they drift apart.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

LICENCE_CODES: tuple[str, ...] = (
    "cc0",
    "cc-by",
    "cc-by-sa",
    "cc-by-nc",
    "cc-by-nd",
    "cc-by-nc-sa",
    "cc-by-nc-nd",
    "other",
    "unknown",
)
"""Normalised licence codes. Only `cc0` and `cc-by` permit full-text reuse."""

REUSABLE_LICENCE_CODES: tuple[str, ...] = ("cc0", "cc-by")

RELATION_TYPES: tuple[str, ...] = (
    "retraction_in",
    "retraction_of",
    "erratum_in",
    "erratum_for",
    "expression_of_concern_in",
    "expression_of_concern_for",
    "comment_in",
    "comment_on",
    "update_in",
    "update_of",
    "republished_in",
    "republished_from",
    "other",
)
"""Normalised bibliographic relation types, from Europe PMC's `commentCorrectionList`."""

RUN_STATUSES: tuple[str, ...] = ("running", "succeeded", "partial", "failed")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    doi: Mapped[str | None] = mapped_column(Text)
    pmid: Mapped[str | None] = mapped_column(Text)
    pmcid: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(Text)
    publication_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    language: Mapped[str | None] = mapped_column(Text)
    published_on: Mapped[date | None] = mapped_column(Date)
    first_indexed_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text)
    source_record: Mapped[dict[str, Any]] = mapped_column(JSONB)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("num_nonnulls(doi, pmid, pmcid) >= 1", name="has_identifier"),
        CheckConstraint(r"doi ~ '^10\.[^[:space:]]+$' AND doi = lower(doi)", name="doi_format"),
        CheckConstraint("pmid ~ '^[1-9][0-9]*$'", name="pmid_format"),
        CheckConstraint("pmcid ~ '^PMC[1-9][0-9]*$'", name="pmcid_format"),
        Index(None, "doi", unique=True),
        Index(None, "pmid", unique=True),
        Index(None, "pmcid", unique=True),
    )


class ArticleLicence(Base):
    __tablename__ = "article_licences"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("articles.id"))
    source: Mapped[str] = mapped_column(Text)
    raw_value: Mapped[str | None] = mapped_column(Text)
    licence_code: Mapped[str] = mapped_column(Text)
    full_text_reuse_allowed: Mapped[bool] = mapped_column(
        Boolean, Computed(_in_list("licence_code", REUSABLE_LICENCE_CODES), persisted=True)
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(_in_list("licence_code", LICENCE_CODES), name="licence_code"),
        Index(None, "article_id", "source", "last_seen_at", "id"),
    )


class ArticleRelation(Base):
    __tablename__ = "article_relations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("articles.id"))
    relation_type: Mapped[str] = mapped_column(Text)
    raw_type: Mapped[str] = mapped_column(Text)
    target_source: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    related_article_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("articles.id"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(_in_list("relation_type", RELATION_TYPES), name="relation_type"),
        Index(
            "uq_article_relations_article_id_target",
            "article_id",
            "raw_type",
            "target_source",
            "target_id",
            unique=True,
        ),
        Index(None, "related_article_id"),
        Index(None, "target_source", "target_id"),
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    agent: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    resume_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in_list("status", RUN_STATUSES), name="status"),
        CheckConstraint("(status = 'running') = (finished_at IS NULL)", name="finished_at"),
        CheckConstraint("resume_count >= 0", name="resume_count"),
        Index(
            "uq_pipeline_runs_one_running_per_agent",
            "agent",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        Index("ix_pipeline_runs_agent_status_started_at", "agent", "status", "started_at"),
    )


class PipelineRunError(Base):
    __tablename__ = "pipeline_run_errors"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pipeline_runs.id"))
    source: Mapped[str] = mapped_column(Text)
    source_record_id: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str] = mapped_column(Text)
    raw_record: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index(None, "run_id"),)
