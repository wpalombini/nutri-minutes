"""The shipped Grader prompt and the `python -m pipeline.grader` entry point."""

import pytest

from pipeline.db.models import (
    DESIGN_CATEGORIES,
    FUNDER_TYPES,
    NOT_GRADABLE_REASONS,
    REVIEW_INCLUDES,
    SPONSOR_ROLES,
)
from pipeline.grader.__main__ import _parse_args, main
from pipeline.grader.grading import MODEL_FACTORS, MODEL_FUNDING_SOURCES, parse_reply
from pipeline.grader.rules import GraderArticle
from pipeline.grader.run import PROMPT_NAME, STAGE, prompt_inputs
from pipeline.models import load_prompt
from tests.grader_helpers import graded, not_gradable


def _article() -> GraderArticle:
    return GraderArticle(1, "A title", "An abstract.", ("Journal Article",), ("Council A",))


def test_prompt_loads_for_the_grader_stage() -> None:
    assert load_prompt(PROMPT_NAME).stage == STAGE


def test_prompt_takes_exactly_the_run_inputs() -> None:
    prompt = load_prompt(PROMPT_NAME)
    assert prompt.placeholders == set(prompt_inputs(_article()))
    content = prompt.render(prompt_inputs(_article()))[-1]["content"]
    assert "An abstract." in content and "Council A" in content


def test_schema_follows_the_table_values() -> None:
    properties = load_prompt(PROMPT_NAME).reply_schema["properties"]
    assert tuple(properties["design_category"]["enum"]) == (*DESIGN_CATEGORIES, "none")
    assert tuple(properties["not_gradable"]["enum"]) == (*NOT_GRADABLE_REASONS, "none")
    assert tuple(properties["review_includes"]["enum"]) == (*REVIEW_INCLUDES, "none")
    assert tuple(properties["funder_type"]["enum"]) == FUNDER_TYPES
    assert tuple(properties["funding_source"]["enum"]) == MODEL_FUNDING_SOURCES
    assert tuple(properties["sponsor_roles"]["items"]["enum"]) == SPONSOR_ROLES
    move = properties["moves"]["items"]["properties"]
    assert tuple(move["factor"]["enum"]) == MODEL_FACTORS


def test_prompt_describes_every_design_and_reason() -> None:
    system = load_prompt(PROMPT_NAME).system or ""
    for value in (*DESIGN_CATEGORIES, *NOT_GRADABLE_REASONS):
        assert f"- {value}:" in system


def test_helper_replies_parse() -> None:
    parse_reply(graded())
    parse_reply(not_gradable())


def test_no_arguments_means_pending_articles() -> None:
    assert _parse_args([]) is None


def test_article_ids_are_deduplicated_and_sorted() -> None:
    assert _parse_args(["--article-id", "7", "--article-id", "3", "--article-id", "7"]) == [3, 7]


@pytest.mark.parametrize("value", ["0", "-2", "abc"])
def test_bad_article_ids_are_rejected(value: str) -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--article-id", value])


def test_missing_key_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert main([]) == 1
