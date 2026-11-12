"""SQLAlchemy models for the tables described in docs/database.md.

Alembic migrations are the source of truth for the schema. These models must match them, and
`alembic check` in CI fails when they drift apart.
"""

from datetime import date, datetime
from decimal import Decimal
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
    Numeric,
    SmallInteger,
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

MODEL_CALL_OUTCOMES: tuple[str, ...] = ("succeeded", "invalid_reply", "error", "refused")

STAGE_STATUSES: tuple[str, ...] = ("done", "failed")
"""An article's status for one agent. Articles with no row haven't been processed yet."""

TOPIC_SLUGS: tuple[str, ...] = (
    "bone-health",
    "muscle-and-strength",
    "falls-and-independence",
    "heart-and-metabolism",
    "brain-health",
    "longevity",
    "genes-and-diet",
)
"""The reader-facing topics, matching `web/content/topics.md`."""

TRIAGE_DECIDERS: tuple[str, ...] = ("rule", "model")

TRIAGE_RULES: tuple[str, ...] = ("retracted", "not_research", "no_abstract", "not_english")
"""The rules in `pipeline.triage.rules`. A new rule needs a migration."""

GRADE_DECIDERS: tuple[str, ...] = ("rule", "model")

DESIGN_CATEGORIES: tuple[str, ...] = (
    "randomised_trial",
    "non_randomised_trial",
    "observational",
    "review",
    "animal",
    "lab",
)
"""Study designs the Grader assigns. The web app owns the reader-facing label for each."""

NOT_GRADABLE_REASONS: tuple[str, ...] = (
    "narrative_review",
    "case_report",
    "protocol",
    "not_a_study",
)
"""Why a paper wasn't graded. Ungraded papers get no summary."""

REVIEW_INCLUDES: tuple[str, ...] = ("randomised_trials", "observational", "mixed", "animal_or_lab")
"""What a review combines, which sets its starting level."""

FUNDER_TYPES: tuple[str, ...] = ("industry", "public", "charity", "none", "not_stated")

FUNDING_SOURCES: tuple[str, ...] = ("abstract", "grant_metadata", "full_text", "not_stated")
"""Where the funding facts came from. `not_stated` means none of them says."""

YES_NO_UNKNOWN: tuple[str, ...] = ("yes", "no", "unknown")

SPONSOR_ROLES: tuple[str, ...] = ("design", "analysis", "writing")

GRADE_FACTORS: tuple[str, ...] = (
    "design",
    "size",
    "duration",
    "population",
    "funding_and_conflicts",
)

REASON_DIRECTIONS: tuple[str, ...] = ("raises", "lowers")

GRADE_STARTING_LEVEL = (
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
"""Starting levels (1 very low to 4 high) by design, as `/how-we-grade` describes them."""


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _text_array(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"ARRAY[{quoted}]::text[]"


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


class ModelCall(Base):
    """One attempt by the model client. See `pipeline.models` and ADR 0005."""

    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pipeline_runs.id"))
    stage: Mapped[str] = mapped_column(Text)
    article_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("articles.id"))
    prompt_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer)
    input_values: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model_requested: Mapped[str] = mapped_column(Text)
    model_answered: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    generation_id: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    raw_reply: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric)
    max_cost_usd: Mapped[Decimal] = mapped_column(Numeric)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in_list("outcome", MODEL_CALL_OUTCOMES), name="outcome"),
        CheckConstraint("attempt >= 1", name="attempt"),
        CheckConstraint("cost_usd >= 0 AND max_cost_usd >= 0", name="costs_not_negative"),
        CheckConstraint(
            "(outcome = 'succeeded') = (raw_reply IS NOT NULL AND error IS NULL)",
            name="succeeded_has_reply",
        ),
        Index(None, "run_id", "stage"),
        Index(None, "article_id"),
    )


class ArticleStage(Base):
    """Each article's status per agent, from Triage onwards. A `failed` row is skipped by later
    runs until a person re-runs that article."""

    __tablename__ = "article_stages"

    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("articles.id"), primary_key=True)
    agent: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pipeline_runs.id"))
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in_list("status", STAGE_STATUSES), name="status"),
        CheckConstraint("(status = 'failed') = (error IS NOT NULL)", name="failed_has_error"),
        Index(None, "agent", "status"),
    )


class TriageDecision(Base):
    """A scope decision for an article. New decisions are added, never written over."""

    __tablename__ = "triage_decisions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("articles.id"))
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pipeline_runs.id"))
    decided_by: Mapped[str] = mapped_column(Text)
    rule: Mapped[str | None] = mapped_column(Text)
    model_call_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("model_calls.id"))
    in_scope: Mapped[bool] = mapped_column(Boolean)
    relevance: Mapped[int | None] = mapped_column(Integer)
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    primary_topic: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in_list("decided_by", TRIAGE_DECIDERS), name="decided_by"),
        CheckConstraint(_in_list("rule", TRIAGE_RULES), name="rule"),
        CheckConstraint(
            "(decided_by = 'rule' AND rule IS NOT NULL AND model_call_id IS NULL "
            "AND relevance IS NULL AND NOT in_scope) OR "
            "(decided_by = 'model' AND rule IS NULL AND model_call_id IS NOT NULL "
            "AND relevance IS NOT NULL)",
            name="decider_fields",
        ),
        CheckConstraint("relevance BETWEEN 1 AND 5", name="relevance"),
        CheckConstraint(f"topics <@ {_text_array(TOPIC_SLUGS)}", name="topics"),
        CheckConstraint(
            "(in_scope AND primary_topic IS NOT NULL AND primary_topic = ANY(topics)) OR "
            "(NOT in_scope AND primary_topic IS NULL AND cardinality(topics) = 0)",
            name="primary_topic",
        ),
        Index(None, "article_id", "id"),
        Index(None, "model_call_id"),
        Index(None, "topics", postgresql_using="gin"),
    )


class EvidenceGrade(Base):
    """An evidence grade for an article's main outcome. New grades are added, never written over.

    The level is the starting level plus the moves in `evidence_grade_reasons`, capped by the
    Grader's code; the checks here hold the parts a single row can show.
    """

    __tablename__ = "evidence_grades"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("articles.id"))
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pipeline_runs.id"))
    decided_by: Mapped[str] = mapped_column(Text)
    model_call_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("model_calls.id"))
    not_gradable: Mapped[str | None] = mapped_column(Text)
    design_category: Mapped[str | None] = mapped_column(Text)
    review_includes: Mapped[str | None] = mapped_column(Text)
    review_reported_level: Mapped[int | None] = mapped_column(SmallInteger)
    starting_level: Mapped[int | None] = mapped_column(SmallInteger)
    level: Mapped[int | None] = mapped_column(SmallInteger)
    main_outcome: Mapped[str | None] = mapped_column(Text)
    participants: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[str | None] = mapped_column(Text)
    population: Mapped[str | None] = mapped_column(Text)
    funder: Mapped[str | None] = mapped_column(Text)
    funder_type: Mapped[str | None] = mapped_column(Text)
    funding_source: Mapped[str | None] = mapped_column(Text)
    funder_sells_product: Mapped[str | None] = mapped_column(Text)
    sponsor_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    conflicts: Mapped[str | None] = mapped_column(Text)
    registered: Mapped[str | None] = mapped_column(Text)
    outcome_switched: Mapped[str | None] = mapped_column(Text)
    surrogate_outcome: Mapped[bool | None] = mapped_column(Boolean)
    funding_lowered: Mapped[bool | None] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in_list("decided_by", GRADE_DECIDERS), name="decided_by"),
        CheckConstraint(
            "(decided_by = 'rule' AND model_call_id IS NULL AND not_gradable IS NOT NULL) OR "
            "(decided_by = 'model' AND model_call_id IS NOT NULL)",
            name="decider_fields",
        ),
        CheckConstraint(_in_list("not_gradable", NOT_GRADABLE_REASONS), name="not_gradable"),
        CheckConstraint(_in_list("design_category", DESIGN_CATEGORIES), name="design_category"),
        CheckConstraint(_in_list("review_includes", REVIEW_INCLUDES), name="review_includes"),
        CheckConstraint(_in_list("funder_type", FUNDER_TYPES), name="funder_type"),
        CheckConstraint(_in_list("funding_source", FUNDING_SOURCES), name="funding_source"),
        CheckConstraint(
            _in_list("funder_sells_product", YES_NO_UNKNOWN), name="funder_sells_product"
        ),
        CheckConstraint(_in_list("registered", YES_NO_UNKNOWN), name="registered"),
        CheckConstraint(_in_list("outcome_switched", YES_NO_UNKNOWN), name="outcome_switched"),
        CheckConstraint(f"sponsor_roles <@ {_text_array(SPONSOR_ROLES)}", name="sponsor_roles"),
        CheckConstraint(
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
            name="graded_fields",
        ),
        CheckConstraint(
            "(design_category = 'review' AND review_includes IS NOT NULL) OR "
            "(design_category IS DISTINCT FROM 'review' AND review_includes IS NULL "
            "AND review_reported_level IS NULL)",
            name="review_fields",
        ),
        CheckConstraint("review_reported_level BETWEEN 1 AND 4", name="review_reported_level"),
        CheckConstraint(GRADE_STARTING_LEVEL, name="starting_level"),
        CheckConstraint(
            "level BETWEEN 1 AND 4 AND level <= starting_level + 1 AND "
            "(level <= starting_level OR (design_category NOT IN ('animal', 'lab') "
            "AND review_includes IS DISTINCT FROM 'animal_or_lab'))",
            name="level",
        ),
        CheckConstraint("participants > 0", name="participants"),
        CheckConstraint(
            "(funding_source = 'not_stated') = (funder_type = 'not_stated')",
            name="funding_not_stated",
        ),
        Index(None, "article_id", "id"),
        Index(None, "model_call_id"),
    )


class EvidenceGradeReason(Base):
    """One reason a grade moved, or a concern listed without moving it (`levels` 0)."""

    __tablename__ = "evidence_grade_reasons"

    grade_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evidence_grades.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    factor: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text)
    levels: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("position >= 1", name="position"),
        CheckConstraint(_in_list("factor", GRADE_FACTORS), name="factor"),
        CheckConstraint(_in_list("direction", REASON_DIRECTIONS), name="direction"),
        CheckConstraint("levels BETWEEN 0 AND 2", name="levels"),
        CheckConstraint("length(reason) > 0", name="reason"),
    )
