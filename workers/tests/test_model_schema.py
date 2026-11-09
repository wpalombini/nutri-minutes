"""The reply schema subset: what loads, and what validates."""

from typing import Any

import pytest

from pipeline.models.schema import SchemaError, check_schema, validate

OBJECT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["a", "b"]},
        "score": {"type": "integer", "minimum": 0, "maximum": 10},
        "share": {"type": ["number", "null"]},
        "tags": {"type": "array", "items": {"type": "string", "minLength": 1}, "maxItems": 2},
        "flag": {"type": "boolean"},
    },
    "required": ["label", "score", "share", "tags", "flag"],
    "additionalProperties": False,
}
VALID: dict[str, Any] = {"label": "a", "score": 3, "share": None, "tags": ["x"], "flag": True}


def test_supported_schema_loads() -> None:
    check_schema(OBJECT)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "pattern": "x"},
        {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
        {"type": "array"},
        {"type": "thing"},
        {"enum": ["a"]},
        {"type": "string", "items": {"type": "string"}},
        {"type": "string", "maxLength": -1},
        {"type": "string", "enum": []},
        {"type": "integer", "minimum": True},
        {"type": "object", "properties": {"a": {"$ref": "#/x"}}, "required": ["a"]},
    ],
)
def test_unsupported_or_loose_schemas_are_rejected(schema: dict[str, Any]) -> None:
    with pytest.raises(SchemaError):
        check_schema(schema)


def test_valid_value_passes() -> None:
    assert validate(VALID, OBJECT) == []
    assert validate({**VALID, "share": 0.5, "score": 10.0}, OBJECT) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"label": "c"}, "$.label: not one of the allowed values"),
        ({"score": 11}, "$.score: above 10"),
        ({"score": 2.5}, "$.score: expected integer, got number"),
        ({"score": True}, "$.score: expected integer, got boolean"),
        ({"flag": 1}, "$.flag: expected boolean, got integer"),
        ({"share": "1"}, "$.share: expected number or null, got string"),
        ({"tags": ["a", "b", "c"]}, "$.tags: more than 2 items"),
        ({"tags": [""]}, "$.tags[0]: shorter than 1 characters"),
        ({"extra": 1}, "$: unexpected 'extra'"),
        ({"share": float("nan")}, "$.share: not a finite number"),
    ],
)
def test_invalid_values_are_reported(change: dict[str, Any], problem: str) -> None:
    assert validate({**VALID, **change}, OBJECT) == [problem]


def test_missing_property_is_reported() -> None:
    value = dict(VALID)
    del value["flag"]
    assert validate(value, OBJECT) == ["$: missing 'flag'"]


def test_enum_doesnt_confuse_booleans_and_numbers() -> None:
    schema = {"type": ["integer", "boolean"], "enum": [1]}
    check_schema(schema)
    assert validate(True, schema) == ["$: not one of the allowed values"]
    assert validate(1, schema) == []
