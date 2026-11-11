"""The shipped Triage prompt and the `python -m pipeline.triage` entry point."""

import pytest

from pipeline.db.models import TOPIC_SLUGS
from pipeline.models import load_prompt
from pipeline.triage.__main__ import _parse_args, main
from pipeline.triage.rules import TriageArticle
from pipeline.triage.run import PROMPT_NAME, STAGE, parse_reply, prompt_inputs


def _article() -> TriageArticle:
    return TriageArticle(1, "A title", "An abstract.", "eng", ("Journal Article",), False)


def test_prompt_loads_for_the_triage_stage() -> None:
    prompt = load_prompt(PROMPT_NAME)
    assert prompt.stage == STAGE


def test_prompt_takes_exactly_the_run_inputs() -> None:
    prompt = load_prompt(PROMPT_NAME)
    assert prompt.placeholders == set(prompt_inputs(_article()))
    messages = prompt.render(prompt_inputs(_article()))
    assert "An abstract." in messages[-1]["content"]


def test_schema_topics_follow_the_topic_list() -> None:
    properties = load_prompt(PROMPT_NAME).reply_schema["properties"]
    assert tuple(properties["topics"]["items"]["enum"]) == TOPIC_SLUGS
    assert tuple(properties["primary_topic"]["enum"]) == (*TOPIC_SLUGS, "none")


def test_prompt_names_every_topic() -> None:
    prompt = load_prompt(PROMPT_NAME)
    for slug in TOPIC_SLUGS:
        assert f"- {slug}:" in (prompt.system or "")


def test_out_of_scope_reply_shape_parses() -> None:
    reply = {
        "reason": "Drug trial.",
        "in_scope": False,
        "relevance": 1,
        "topics": [],
        "primary_topic": "none",
    }
    assert parse_reply(reply).in_scope is False


def test_no_arguments_means_pending_articles() -> None:
    assert _parse_args([]) is None


def test_article_ids_are_deduplicated_and_sorted() -> None:
    assert _parse_args(["--article-id", "7", "--article-id", "3", "--article-id", "7"]) == [3, 7]


@pytest.mark.parametrize("value", ["0", "-2", "abc", "1.5"])
def test_bad_article_ids_are_rejected(value: str) -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--article-id", value])


def test_missing_key_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert main([]) == 1
