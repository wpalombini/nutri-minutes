"""Rules Triage applies before calling a model, so clear cases cost nothing.

Each rule only ever drops an article. Anything the rules don't catch goes to the model.
"""

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True)
class TriageArticle:
    id: int
    title: str
    abstract: str | None
    language: str | None
    publication_types: tuple[str, ...]
    retracted: bool
    """A retraction notice points at it, or the source labels it a retracted publication."""


class Rule(StrEnum):
    RETRACTED = "retracted"
    NOT_RESEARCH = "not_research"
    NO_ABSTRACT = "no_abstract"
    NOT_ENGLISH = "not_english"


@dataclass(frozen=True)
class RuleDecision:
    rule: Rule
    reason: str


NON_RESEARCH_TYPES = frozenset(
    {
        "editorial",
        "letter",
        "comment",
        "article-commentary",
        "published erratum",
        "erratum",
        "correction",
        "retraction of publication",
        "retraction",
        "expression of concern",
        "news",
        "interview",
        "biography",
        "portrait",
    }
)
"""Publication types that aren't reports of research, compared in lower case. Europe PMC mixes
PubMed's types with the journal's own, such as `article-commentary`."""

RESEARCH_TYPES = frozenset(
    {
        "randomized controlled trial",
        "clinical trial",
        "controlled clinical trial",
        "pragmatic clinical trial",
        "meta-analysis",
        "systematic review",
        "systematic-review",
        "review",
        "review-article",
        "observational study",
        "research-article",
    }
)
"""Types that mark a research report. An article with one is never dropped as not research,
so a research letter with a trial in it still reaches the model."""

RULES_VERSION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
"""A hash of this file, stored with each run, so decisions trace to the rules behind them."""

RETRACTED_TYPES = frozenset({"retracted publication"})
ENGLISH = "eng"


def is_retracted_type(publication_types: tuple[str, ...]) -> bool:
    return any(t.strip().lower() in RETRACTED_TYPES for t in publication_types)


def apply_rules(article: TriageArticle) -> RuleDecision | None:
    """The first rule that drops the article, or None if the model should decide."""
    types = {t.strip().lower() for t in article.publication_types}
    if article.retracted:
        return RuleDecision(Rule.RETRACTED, "The article has been retracted.")
    non_research = sorted(types & NON_RESEARCH_TYPES)
    if non_research and not types & RESEARCH_TYPES:
        return RuleDecision(Rule.NOT_RESEARCH, f"Not a research report: {', '.join(non_research)}.")
    if article.abstract is None or not article.abstract.strip():
        return RuleDecision(Rule.NO_ABSTRACT, "The article has no abstract to work from.")
    if article.language is not None and article.language.strip().lower() != ENGLISH:
        return RuleDecision(
            Rule.NOT_ENGLISH, f"The article is in another language: {article.language}."
        )
    return None
