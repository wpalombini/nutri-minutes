"""Loading, versioning and rendering prompts."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pipeline.models.prompts import PromptError, load_prompt
from tests.prompt_files import REPLY_SCHEMA, settings, write_prompt


def test_loads_and_renders(tmp_path: Path) -> None:
    prompt = write_prompt(tmp_path)
    assert prompt.stage == "triage"
    assert prompt.model == "example/model-1.0"
    assert prompt.price_caps.completion_per_million == Decimal("4.00")
    assert prompt.placeholders == {"title", "abstract"}
    messages = prompt.render({"title": "T {{ abstract }}", "abstract": "A"})
    assert messages == [
        {"role": "system", "content": "You classify papers."},
        {"role": "user", "content": "Title: T {{ abstract }}\nAbstract: A"},
    ]


def test_inputs_must_match_placeholders(tmp_path: Path) -> None:
    prompt = write_prompt(tmp_path)
    with pytest.raises(PromptError, match=r"missing inputs \['abstract'\]"):
        prompt.render({"title": "T"})
    with pytest.raises(PromptError, match=r"unexpected inputs \['extra'\]"):
        prompt.render({"title": "T", "abstract": "A", "extra": "x"})


def test_version_follows_content(tmp_path: Path) -> None:
    first = write_prompt(tmp_path / "a")
    same = write_prompt(tmp_path / "b")
    other_template = write_prompt(tmp_path / "c", template="--- user ---\n{{ title }}\n")
    other_model = write_prompt(tmp_path / "d", prompt_settings=settings(model="example/model-2"))
    assert first.version == same.version
    assert len({first.version, other_template.version, other_model.version}) == 3


def test_user_section_alone(tmp_path: Path) -> None:
    prompt = write_prompt(tmp_path, template="--- user ---\nHello {{ name }}\n")
    assert prompt.system is None
    assert prompt.render({"name": "x"}) == [{"role": "user", "content": "Hello x"}]


@pytest.mark.parametrize(
    "template",
    [
        "No sections",
        "--- user ---\nA\n--- system ---\nB\n",
        "--- system ---\nA\n",
        "Preamble\n--- user ---\nA\n",
        "--- system ---\n\n--- user ---\nA\n",
    ],
)
def test_bad_templates_are_rejected(tmp_path: Path, template: str) -> None:
    with pytest.raises(PromptError):
        write_prompt(tmp_path, template=template)


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": "~example/model-latest"},
        {"model": "openrouter/auto"},
        {"model": "example/model-latest"},
        {"model": "no-slash"},
        {"max_tokens": 0},
        {"max_tokens": True},
        {"temperature": "0"},
        {"price_caps": {"prompt": 1, "completion": "1", "request": "0"}},
        {"price_caps": {"prompt": "1", "completion": "1"}},
        {"price_caps": {"prompt": "-1", "completion": "1", "request": "0"}},
        {"price_caps": {"prompt": "NaN", "completion": "1", "request": "0"}},
        {"reasoning": {"effort": "low", "max_tokens": 100}},
        {"reasoning": {"effort": "huge"}},
        {"reasoning": {"effort": "low", "counted_separately": True}},
        {"reply_schema": {"type": "string"}},
        {"reply_schema": {**REPLY_SCHEMA, "additionalProperties": True}},
        {"unknown": 1},
    ],
)
def test_bad_settings_are_rejected(tmp_path: Path, overrides: dict[str, Any]) -> None:
    with pytest.raises(PromptError):
        write_prompt(tmp_path, prompt_settings=settings(**overrides))


def test_settings_must_be_json(tmp_path: Path) -> None:
    write_prompt(tmp_path)
    (tmp_path / "triage" / "scope.json").write_text("{", encoding="utf-8")
    with pytest.raises(PromptError, match="valid JSON"):
        load_prompt("triage/scope", tmp_path)


@pytest.mark.parametrize("name", ["triage", "../x/y", "Triage/scope", "triage/scope/x"])
def test_bad_names_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(PromptError, match="Not a prompt name"):
        load_prompt(name, tmp_path)


def test_missing_prompt(tmp_path: Path) -> None:
    with pytest.raises(PromptError, match="not found"):
        load_prompt("triage/none", tmp_path)


def test_reasoning_field(tmp_path: Path) -> None:
    prompt = write_prompt(
        tmp_path,
        prompt_settings=settings(
            reasoning={"max_tokens": 2000, "exclude": True, "counted_separately": True}
        ),
    )
    assert prompt.reasoning is not None
    assert prompt.reasoning.request_field() == {"max_tokens": 2000, "exclude": True}


def test_shipped_prompts_load() -> None:
    prompt = load_prompt("diagnostics/cost_check")
    assert prompt.placeholders == {"word"}
    assert json.dumps(prompt.reply_schema)
