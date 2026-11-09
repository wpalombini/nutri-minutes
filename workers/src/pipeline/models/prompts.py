"""Prompts as code (ADR 0005): a template and a settings file per prompt.

A prompt named `<stage>/<name>` lives in `pipeline/prompts/<stage>/` as `<name>.md`, the
template, and `<name>.json`, its settings. The template has an optional `--- system ---`
section followed by a `--- user ---` section, each on a line of its own. Placeholders look like
`{{ abstract }}`, and a call must supply exactly the placeholders the template uses.

The settings file holds:
- `model`: an explicit OpenRouter model ID, never a floating alias.
- `max_tokens`: the reply limit, which must include any reasoning tokens.
- `temperature`: optional.
- `price_caps`: US dollars, as strings, with `prompt` and `completion` per million tokens and
  `request` per request. Providers that charge more aren't used.
- `reasoning`: optional, with `effort` or `max_tokens`, and `exclude`. For a model whose reasoning
  tokens don't count within `max_tokens`, set `max_tokens` here and `counted_separately: true`,
  so the budget check adds them.
- `reply_schema`: the JSON Schema every reply must match (see `schema.py`).

The version is a hash of the template and the settings, so any change gives a new version.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from pipeline.models.schema import SchemaError, check_schema

NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]*/[a-z][a-z0-9_]*")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
MODEL_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:-]*")
SYSTEM_MARKER = "--- system ---"
USER_MARKER = "--- user ---"
SETTINGS_KEYS = frozenset(
    {"model", "max_tokens", "temperature", "price_caps", "reasoning", "reply_schema"}
)
PRICE_KEYS = frozenset({"prompt", "completion", "request"})
REASONING_KEYS = frozenset({"effort", "max_tokens", "exclude", "counted_separately"})
EFFORTS = frozenset({"max", "xhigh", "high", "medium", "low", "minimal", "none"})


class PromptError(ValueError):
    """A prompt is missing, malformed or called with the wrong inputs."""


@dataclass(frozen=True)
class PriceCaps:
    prompt_per_million: Decimal
    completion_per_million: Decimal
    per_request: Decimal


@dataclass(frozen=True)
class Reasoning:
    effort: str | None
    max_tokens: int | None
    exclude: bool
    counted_separately: bool

    def request_field(self) -> dict[str, Any]:
        field: dict[str, Any] = {}
        if self.effort is not None:
            field["effort"] = self.effort
        if self.max_tokens is not None:
            field["max_tokens"] = self.max_tokens
        if self.exclude:
            field["exclude"] = True
        return field


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    model: str
    max_tokens: int
    temperature: float | None
    price_caps: PriceCaps
    reasoning: Reasoning | None
    reply_schema: dict[str, Any]
    system: str | None
    user: str

    @property
    def stage(self) -> str:
        return self.name.split("/", 1)[0]

    @property
    def placeholders(self) -> frozenset[str]:
        return frozenset(PLACEHOLDER.findall((self.system or "") + "\n" + self.user))

    def render(self, inputs: Mapping[str, str]) -> list[dict[str, str]]:
        """The chat messages for these inputs. Values are inserted as they are, in one pass."""
        missing = self.placeholders - set(inputs)
        extra = set(inputs) - self.placeholders
        if missing or extra:
            raise PromptError(
                f"{self.name}: missing inputs {sorted(missing)}, unexpected inputs {sorted(extra)}"
            )
        for key, value in inputs.items():
            if not isinstance(value, str):
                raise PromptError(f"{self.name}: input '{key}' must be a string")

        def fill(template: str) -> str:
            return PLACEHOLDER.sub(lambda match: inputs[match.group(1)], template)

        messages = []
        if self.system is not None:
            messages.append({"role": "system", "content": fill(self.system)})
        messages.append({"role": "user", "content": fill(self.user)})
        return messages


def _default_root() -> Traversable:
    return files("pipeline.prompts")


def load_prompt(name: str, root: Traversable | Path | None = None) -> Prompt:
    if not NAME_PATTERN.fullmatch(name):
        raise PromptError(f"Not a prompt name: {name!r}")
    stage, base = name.split("/")
    folder = (root if root is not None else _default_root()) / stage
    try:
        template = (folder / f"{base}.md").read_bytes()
        raw_settings = (folder / f"{base}.json").read_bytes()
    except FileNotFoundError as exc:
        raise PromptError(f"{name}: prompt files not found") from exc
    try:
        settings = json.loads(raw_settings)
    except ValueError as exc:
        raise PromptError(f"{name}: settings aren't valid JSON") from exc
    try:
        text = template.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PromptError(f"{name}: template isn't UTF-8") from exc
    return _build(name, text, settings, _version(template, settings))


def _version(template: bytes, settings: Any) -> str:
    digest = hashlib.sha256()
    digest.update(b"template\0")
    digest.update(template)
    digest.update(b"\0settings\0")
    digest.update(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()[:16]


def _sections(name: str, text: str) -> tuple[str | None, str]:
    lines = text.splitlines()
    markers = [i for i, line in enumerate(lines) if line.strip() in {SYSTEM_MARKER, USER_MARKER}]
    labels = [lines[i].strip() for i in markers]
    if labels not in ([USER_MARKER], [SYSTEM_MARKER, USER_MARKER]):
        raise PromptError(f"{name}: template needs an optional system section, then a user one")
    if any(line.strip() for line in lines[: markers[0]]):
        raise PromptError(f"{name}: text before the first section")
    bounds = [*markers, len(lines)]
    bodies = ["\n".join(lines[bounds[i] + 1 : bounds[i + 1]]).strip() for i in range(len(markers))]
    if not all(bodies):
        raise PromptError(f"{name}: empty section")
    return (bodies[0], bodies[1]) if len(bodies) == 2 else (None, bodies[0])


def _price(name: str, caps: dict[str, Any], key: str) -> Decimal:
    value = caps.get(key)
    if not isinstance(value, str):
        raise PromptError(f'{name}: price_caps.{key} must be a string, such as "0.50"')
    try:
        price = Decimal(value)
    except InvalidOperation as exc:
        raise PromptError(f"{name}: price_caps.{key} isn't a number") from exc
    if not price.is_finite() or price < 0:
        raise PromptError(f"{name}: price_caps.{key} must be zero or more")
    return price


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _reasoning(name: str, raw: Any) -> Reasoning | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) - REASONING_KEYS:
        raise PromptError(f"{name}: reasoning may only have {sorted(REASONING_KEYS)}")
    effort, max_tokens = raw.get("effort"), raw.get("max_tokens")
    if (effort is None) == (max_tokens is None):
        raise PromptError(f"{name}: reasoning needs exactly one of effort and max_tokens")
    if effort is not None and effort not in EFFORTS:
        raise PromptError(f"{name}: reasoning.effort must be one of {sorted(EFFORTS)}")
    if max_tokens is not None and not _positive_int(max_tokens):
        raise PromptError(f"{name}: reasoning.max_tokens must be a positive whole number")
    exclude, separate = raw.get("exclude", False), raw.get("counted_separately", False)
    if not isinstance(exclude, bool) or not isinstance(separate, bool):
        raise PromptError(f"{name}: reasoning.exclude and counted_separately must be true or false")
    if separate and max_tokens is None:
        raise PromptError(f"{name}: counted_separately needs reasoning.max_tokens")
    return Reasoning(effort, max_tokens, exclude, separate)


def _build(name: str, text: str, settings: Any, version: str) -> Prompt:
    if not isinstance(settings, dict):
        raise PromptError(f"{name}: settings must be a JSON object")
    unknown = set(settings) - SETTINGS_KEYS
    if unknown:
        raise PromptError(f"{name}: unknown settings {sorted(unknown)}")
    model = settings.get("model")
    if (
        not isinstance(model, str)
        or not MODEL_PATTERN.fullmatch(model)
        or model.startswith("openrouter/")
        or "latest" in model
    ):
        raise PromptError(f"{name}: model must be an explicit model ID, not an alias")
    max_tokens = settings.get("max_tokens")
    if not isinstance(max_tokens, int) or not _positive_int(max_tokens):
        raise PromptError(f"{name}: max_tokens must be a positive whole number")
    temperature = settings.get("temperature")
    if temperature is not None and (
        isinstance(temperature, bool) or not isinstance(temperature, int | float)
    ):
        raise PromptError(f"{name}: temperature must be a number")
    caps = settings.get("price_caps")
    if not isinstance(caps, dict) or set(caps) != PRICE_KEYS:
        raise PromptError(f"{name}: price_caps needs exactly {sorted(PRICE_KEYS)}")
    reply_schema = settings.get("reply_schema")
    try:
        check_schema(reply_schema)
    except SchemaError as exc:
        raise PromptError(f"{name}: reply_schema: {exc}") from exc
    if not isinstance(reply_schema, dict) or reply_schema.get("type") != "object":
        raise PromptError(f"{name}: reply_schema must describe an object")
    system, user = _sections(name, text)
    return Prompt(
        name=name,
        version=version,
        model=model,
        max_tokens=max_tokens,
        temperature=float(temperature) if temperature is not None else None,
        price_caps=PriceCaps(
            prompt_per_million=_price(name, caps, "prompt"),
            completion_per_million=_price(name, caps, "completion"),
            per_request=_price(name, caps, "request"),
        ),
        reasoning=_reasoning(name, settings.get("reasoning")),
        reply_schema=reply_schema,
        system=system,
        user=user,
    )
