"""Triage's rules before the model, and how it reads model replies."""

from typing import Any

import pytest

from pipeline.triage.rules import Rule, TriageArticle, apply_rules, is_retracted_type
from pipeline.triage.run import ReplyError, parse_reply, prompt_inputs
from tests.triage_helpers import in_scope, out_of_scope


def article(**overrides: Any) -> TriageArticle:
    values: dict[str, Any] = {
        "id": 1,
        "title": "Protein and muscle in older adults",
        "abstract": "Synthetic abstract.",
        "language": "eng",
        "publication_types": ("Journal Article", "Randomized Controlled Trial"),
        "retracted": False,
    }
    values.update(overrides)
    return TriageArticle(**values)


def test_research_with_an_abstract_goes_to_the_model() -> None:
    assert apply_rules(article()) is None


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"retracted": True}, Rule.RETRACTED),
        ({"publication_types": ("Editorial",)}, Rule.NOT_RESEARCH),
        ({"publication_types": ("Journal Article", "Published Erratum")}, Rule.NOT_RESEARCH),
        ({"publication_types": ("article-commentary",)}, Rule.NOT_RESEARCH),
        ({"publication_types": (" LETTER ",)}, Rule.NOT_RESEARCH),
        ({"abstract": None}, Rule.NO_ABSTRACT),
        ({"abstract": "  \n"}, Rule.NO_ABSTRACT),
        ({"language": "ger"}, Rule.NOT_ENGLISH),
    ],
)
def test_rules_drop_clear_cases(overrides: dict[str, Any], rule: Rule) -> None:
    decision = apply_rules(article(**overrides))
    assert decision is not None and decision.rule is rule
    assert decision.reason


def test_retraction_is_checked_first() -> None:
    decision = apply_rules(article(retracted=True, abstract=None, publication_types=("Letter",)))
    assert decision is not None and decision.rule is Rule.RETRACTED


def test_a_research_letter_still_goes_to_the_model() -> None:
    types = ("Letter", "Randomized Controlled Trial")
    assert apply_rules(article(publication_types=types)) is None


def test_missing_language_and_types_go_to_the_model() -> None:
    assert apply_rules(article(language=None, publication_types=())) is None


def test_retracted_publication_type() -> None:
    assert is_retracted_type(("Journal Article", "Retracted Publication"))
    assert not is_retracted_type(("Journal Article",))


def test_prompt_inputs() -> None:
    inputs = prompt_inputs(article(publication_types=()))
    assert inputs == {
        "title": "Protein and muscle in older adults",
        "abstract": "Synthetic abstract.",
        "publication_types": "not given",
    }


def test_parse_in_scope_reply_puts_primary_topic_first() -> None:
    reply = in_scope("muscle-and-strength", "bone-health")
    reply["topics"] = ["bone-health"]
    decision = parse_reply(reply)
    assert decision.in_scope
    assert decision.topics == ("muscle-and-strength", "bone-health")
    assert decision.primary_topic == "muscle-and-strength"


def test_parse_out_of_scope_reply_keeps_no_topics() -> None:
    reply = out_of_scope()
    reply["topics"] = ["longevity"]
    decision = parse_reply(reply)
    assert (decision.in_scope, decision.topics, decision.primary_topic) == (False, (), None)


@pytest.mark.parametrize(
    "change",
    [
        {"primary_topic": "none"},
        {"topics": ["bone-health", "sport"]},
        {"relevance": 0},
        {"relevance": True},
        {"reason": " "},
        {"in_scope": "yes"},
    ],
)
def test_parse_rejects_replies_that_make_no_sense(change: dict[str, Any]) -> None:
    with pytest.raises(ReplyError):
        parse_reply({**in_scope(), **change})
