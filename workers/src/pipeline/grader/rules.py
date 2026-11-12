"""Rules the Evidence Grader applies before calling a model, so clear cases cost nothing.

A rule only ever marks a paper as not gradable. Anything the rules don't catch goes to the model.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GraderArticle:
    id: int
    title: str
    abstract: str | None
    publication_types: tuple[str, ...]
    grant_agencies: tuple[str, ...]
    """Funders from Europe PMC's grant list, deduplicated in their listed order."""


@dataclass(frozen=True)
class RuleDecision:
    not_gradable: str
    reason: str


CASE_REPORT_TYPES = frozenset({"case reports", "case-report", "case-study"})
PROTOCOL_TYPES = frozenset({"clinical trial protocol", "study-protocol"})
STUDY_TYPES = frozenset(
    {
        "randomized controlled trial",
        "clinical trial",
        "controlled clinical trial",
        "pragmatic clinical trial",
        "observational study",
        "meta-analysis",
        "network meta-analysis",
        "systematic review",
        "systematic-review",
    }
)
"""Types that report a study of more than one person. A paper with one of them goes to the model
even when it also carries a case report or protocol type."""

HUMAN_TRIAL_TYPES = frozenset(
    {
        "randomized controlled trial",
        "clinical trial",
        "controlled clinical trial",
        "pragmatic clinical trial",
        "clinical trial, phase i",
        "clinical trial, phase ii",
        "clinical trial, phase iii",
        "clinical trial, phase iv",
        "multicenter study",
    }
)
"""PubMed types given only to studies in people, so their designs can't be animal or lab."""

REVIEW_TYPES = frozenset({"meta-analysis", "network meta-analysis", "systematic review"})
"""PubMed types given only to reviews that combine studies."""

RULES_VERSION = "1"
"""Bump when a rule changes, so runs record which rules decided."""


def _types(article: GraderArticle) -> set[str]:
    return {t.strip().lower() for t in article.publication_types}


def apply_rules(article: GraderArticle) -> RuleDecision | None:
    types = _types(article)
    if types & STUDY_TYPES:
        return None
    if types & CASE_REPORT_TYPES:
        return RuleDecision("case_report", "Publication type is a case report.")
    if types & PROTOCOL_TYPES:
        return RuleDecision("protocol", "Publication type is a study protocol, with no results.")
    return None


def design_conflict(article: GraderArticle, design_category: str) -> str | None:
    """Why a design contradicts the publication types, or None. The types are set by indexers,
    so a contradiction means the model misread the paper."""
    types = _types(article)
    if types & HUMAN_TRIAL_TYPES and design_category in ("animal", "lab"):
        return f"Publication types say a study in people, but the design is {design_category}"
    if types & REVIEW_TYPES and design_category != "review":
        return f"Publication types say a review, but the design is {design_category}"
    return None
