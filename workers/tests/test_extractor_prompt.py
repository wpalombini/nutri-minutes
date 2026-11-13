"""The shipped Extractor prompt and the `python -m pipeline.extractor` entry point."""

import pytest

from pipeline.db.models import EFFECT_MEASURES, EXTRACTION_FACT_KINDS
from pipeline.extractor.__main__ import _parse_args, main
from pipeline.extractor.extraction import EFFECT_FIELDS, NO_MEASURE, parse_reply
from pipeline.extractor.run import PROMPT_NAME, STAGE, ExtractorArticle, prompt_inputs
from pipeline.models import load_prompt
from tests.extractor_helpers import ABSTRACT, NO_EFFECT, extracted


def _article() -> ExtractorArticle:
    return ExtractorArticle(
        1,
        "A title",
        "An abstract.",
        ("Journal Article",),
        7,
        "randomised trial",
        "hip fracture",
        None,
        "3 years",
        None,
    )


def test_prompt_loads_for_the_extractor_stage() -> None:
    assert load_prompt(PROMPT_NAME).stage == STAGE


def test_prompt_takes_exactly_the_run_inputs() -> None:
    prompt = load_prompt(PROMPT_NAME)
    inputs = prompt_inputs(_article())
    assert prompt.placeholders == set(inputs)
    assert inputs["participants"] == "not stated" and inputs["population"] == "not stated"
    content = prompt.render(inputs)[-1]["content"]
    assert "An abstract." in content and "hip fracture" in content


def test_schema_follows_the_table_values() -> None:
    properties = load_prompt(PROMPT_NAME).reply_schema["properties"]
    assert tuple(properties["measure"]["enum"]) == (*EFFECT_MEASURES, NO_MEASURE)
    assert tuple(properties["facts"]["items"]["properties"]["kind"]["enum"]) == (
        EXTRACTION_FACT_KINDS
    )
    for field in EFFECT_FIELDS:
        assert "null" in properties[field]["type"]


def test_prompt_describes_every_measure_and_kind() -> None:
    system = load_prompt(PROMPT_NAME).system or ""
    for value in (*EFFECT_MEASURES, *EXTRACTION_FACT_KINDS):
        assert f"- {value}:" in system


def test_helper_replies_parse() -> None:
    parse_reply(extracted(), ABSTRACT)
    parse_reply(extracted(**NO_EFFECT), ABSTRACT)


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
