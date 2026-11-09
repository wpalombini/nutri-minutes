"""Writing prompt files into a temporary folder for tests."""

import copy
import json
from pathlib import Path
from typing import Any

from pipeline.models.prompts import Prompt, load_prompt

TEMPLATE = """--- system ---
You classify papers.

--- user ---
Title: {{ title }}
Abstract: {{abstract}}
"""

REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "in_scope": {"type": "boolean"},
        "reason": {"type": "string", "maxLength": 200},
    },
    "required": ["in_scope", "reason"],
    "additionalProperties": False,
}

SETTINGS: dict[str, Any] = {
    "model": "example/model-1.0",
    "max_tokens": 1000,
    "temperature": 0,
    "price_caps": {"prompt": "1.00", "completion": "4.00", "request": "0"},
    "reply_schema": REPLY_SCHEMA,
}


def settings(**overrides: Any) -> dict[str, Any]:
    values = copy.deepcopy(SETTINGS)
    values.update(overrides)
    return values


def write_prompt(
    root: Path,
    name: str = "triage/scope",
    template: str = TEMPLATE,
    prompt_settings: Any = None,
) -> Prompt:
    stage, base = name.split("/")
    folder = root / stage
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{base}.md").write_text(template, encoding="utf-8")
    raw = prompt_settings if prompt_settings is not None else SETTINGS
    (folder / f"{base}.json").write_text(json.dumps(raw), encoding="utf-8")
    return load_prompt(name, root)
