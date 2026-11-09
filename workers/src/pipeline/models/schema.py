"""A small JSON Schema subset for reply schemas, checked when a prompt loads.

Replies are validated locally because some providers treat the schema as a hint. Only the
keywords below are allowed, and objects must list every property as required and forbid extra
ones, which is what strict structured output expects. A schema using anything else is rejected
when the prompt loads, so a keyword this validator ignores can never let a bad reply through.
"""

import math
from typing import Any

TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})
KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "description",
        "title",
    }
)
MAX_PROBLEMS = 20


class SchemaError(ValueError):
    """A reply schema uses something this validator doesn't support."""


def _types(schema: dict[str, Any]) -> list[str]:
    declared = schema.get("type")
    return [declared] if isinstance(declared, str) else list(declared or [])


def check_schema(schema: Any, path: str = "$") -> None:
    """Raise `SchemaError` unless the schema sticks to the supported, strict subset."""
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: a schema must be an object")
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise SchemaError(f"{path}: unsupported keywords {sorted(unknown)}")
    types = _types(schema)
    if not types or any(t not in TYPES for t in types) or len(set(types)) != len(types):
        raise SchemaError(f"{path}: 'type' must name one or more JSON types")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise SchemaError(f"{path}: 'enum' must be a non-empty list")
    if "object" in types:
        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            raise SchemaError(f"{path}: an object must define 'properties'")
        if schema.get("additionalProperties") is not False:
            raise SchemaError(f"{path}: an object must set 'additionalProperties' to false")
        required = schema.get("required")
        if (
            not isinstance(required, list)
            or not all(isinstance(name, str) for name in required)
            or len(required) != len(set(required))
            or set(required) != set(properties)
        ):
            raise SchemaError(f"{path}: 'required' must list every property")
        for name, child in properties.items():
            check_schema(child, f"{path}.{name}")
    elif "properties" in schema or "required" in schema or "additionalProperties" in schema:
        raise SchemaError(f"{path}: object keywords on a non-object type")
    if "array" in types:
        if "items" not in schema:
            raise SchemaError(f"{path}: an array must define 'items'")
        check_schema(schema["items"], f"{path}[]")
    elif "items" in schema:
        raise SchemaError(f"{path}: 'items' on a non-array type")
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        value = schema.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise SchemaError(f"{path}: '{key}' must be a non-negative whole number")
    for key in ("minimum", "maximum"):
        value = schema.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int | float)):
            raise SchemaError(f"{path}: '{key}' must be a number")
    for low, high in (("minimum", "maximum"), ("minLength", "maxLength"), ("minItems", "maxItems")):
        if low in schema and high in schema and schema[low] > schema[high]:
            raise SchemaError(f"{path}: '{low}' is above '{high}'")
    for option in schema.get("enum", []):
        kind = _type_of(option)
        if kind not in types and not (kind == "integer" and "number" in types):
            raise SchemaError(f"{path}: enum value of type {kind} doesn't match 'type'")


def _type_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "integer" if value.is_integer() else "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _same(a: Any, b: Any) -> bool:
    """JSON equality: unlike Python, `true` is not equal to `1`."""
    return _type_of(a) == _type_of(b) and a == b


def validate(value: Any, schema: dict[str, Any]) -> list[str]:
    """Problems with `value` against a schema that passed `check_schema`; empty when valid."""
    problems: list[str] = []
    _validate(value, schema, "$", problems)
    return problems[:MAX_PROBLEMS]


def _validate(value: Any, schema: dict[str, Any], path: str, problems: list[str]) -> None:
    if len(problems) >= MAX_PROBLEMS:
        return
    actual = _type_of(value)
    types = _types(schema)
    if isinstance(value, float) and not math.isfinite(value):
        problems.append(f"{path}: not a finite number")
        return
    if actual not in types and not (actual == "integer" and "number" in types):
        problems.append(f"{path}: expected {' or '.join(types)}, got {actual}")
        return
    if "enum" in schema and not any(_same(value, option) for option in schema["enum"]):
        problems.append(f"{path}: not one of the allowed values")
    if actual == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{path}: longer than {schema['maxLength']} characters")
    elif actual in {"integer", "number"}:
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: above {schema['maximum']}")
    elif actual == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{path}: more than {schema['maxItems']} items")
        for index, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{index}]", problems)
    elif actual == "object":
        properties: dict[str, Any] = schema["properties"]
        for name in properties:
            if name not in value:
                problems.append(f"{path}: missing '{name}'")
        for name in value:
            if name not in properties:
                problems.append(f"{path}: unexpected '{name}'")
        for name, child in properties.items():
            if name in value:
                _validate(value[name], child, f"{path}.{name}", problems)
