"""The shipped Writer prompt and the `python -m pipeline.writer` entry point."""

import pytest

from pipeline.models import load_prompt
from pipeline.writer.__main__ import _parse_args, main
from pipeline.writer.run import PROMPT_NAME, STAGE, prompt_inputs
from pipeline.writer.writing import MAX_PARAGRAPHS, SHOWN_LIMITS_MAX
from tests.test_writer_writing import ARTICLE


def test_prompt_loads_for_the_writer_stage() -> None:
    assert load_prompt(PROMPT_NAME).stage == STAGE


def test_prompt_takes_exactly_the_run_inputs() -> None:
    prompt = load_prompt(PROMPT_NAME)
    inputs = prompt_inputs(ARTICLE)
    assert prompt.placeholders == set(inputs)
    content = prompt.render(inputs)[-1]["content"]
    assert "Hazard ratio 0.80" in content and "Adherence was self-reported." in content


def test_schema_allows_what_the_checks_allow() -> None:
    properties = load_prompt(PROMPT_NAME).reply_schema["properties"]
    assert properties["paragraphs"]["maxItems"] == MAX_PARAGRAPHS
    assert properties["limits"]["maxItems"] == SHOWN_LIMITS_MAX
    assert "null" in properties["absolute_sentence"]["type"]


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
