from __future__ import annotations

import ast

import pytest

from astichi.model import MAX_EXTERNAL_VALUE_DEPTH, validate_external_value, value_to_ast


@pytest.mark.parametrize(
    ("value", "expected_source"),
    [
        (3, "3"),
        (3.14, "3.14"),
        ("row", "'row'"),
        (True, "True"),
        (False, "False"),
        (None, "None"),
        ((), "()"),
        ([], "[]"),
        ((1, 2, 3), "(1, 2, 3)"),
        ([1, 2, 3], "[1, 2, 3]"),
        ((1, ("nested", "tuple")), "(1, ('nested', 'tuple'))"),
        ([1, [2, None], ("x", False)], "[1, [2, None], ('x', False)]"),
        ({"k": "v"}, "{'k': 'v'}"),
        (
            {"left": [1, 2], "right": ("x", {"nested": True})},
            "{'left': [1, 2], 'right': ('x', {'nested': True})}",
        ),
    ],
)
def test_value_to_ast_round_trips_supported_v1_values(
    value: object,
    expected_source: str,
) -> None:
    converted = value_to_ast(value)

    assert isinstance(converted, ast.expr)
    assert ast.unparse(converted) == expected_source


@pytest.mark.parametrize(
    "value",
    [
        3,
        3.14,
        "row",
        True,
        None,
        (1, ("nested", "tuple")),
        [1, [2, None], ("x", False)],
        {"k": "v"},
        {"left": [1, 2], "right": ("x", {"nested": True})},
    ],
)
def test_validate_external_value_accepts_supported_v1_values(value: object) -> None:
    validate_external_value(value)


def test_value_to_ast_preserves_bool_and_int_types() -> None:
    true_node = value_to_ast(True)
    one_node = value_to_ast(1)

    assert isinstance(true_node, ast.Constant)
    assert isinstance(one_node, ast.Constant)
    assert type(true_node.value) is bool
    assert type(one_node.value) is int


@pytest.mark.parametrize(
    ("value", "expected_type_name"),
    [
        ({"a", "b"}, "set"),
        (object(), "object"),
        (lambda value: value, "function"),
        (b"bytes", "bytes"),
        (1 + 2j, "complex"),
    ],
)
def test_value_to_ast_rejects_unsupported_v1_values(
    value: object,
    expected_type_name: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=rf"unsupported external binding value type .*: {expected_type_name}",
    ):
        value_to_ast(value)


def test_value_to_ast_enforces_depth_limit() -> None:
    value: object = 0
    for _ in range(MAX_EXTERNAL_VALUE_DEPTH + 1):
        value = [value]

    with pytest.raises(
        ValueError,
        match=rf"external binding value exceeds max depth {MAX_EXTERNAL_VALUE_DEPTH}",
    ):
        value_to_ast(value)


def test_value_to_ast_accepts_max_allowed_depth() -> None:
    value: object = 0
    for _ in range(MAX_EXTERNAL_VALUE_DEPTH):
        value = [value]

    converted = value_to_ast(value)

    assert isinstance(converted, ast.List)


def test_value_to_ast_rejects_recursive_sequence() -> None:
    recursive: list[object] = []
    recursive.append(recursive)

    with pytest.raises(
        ValueError,
        match=r"recursive external binding value is not supported at value\[0\]",
    ):
        value_to_ast(recursive)


def test_value_to_ast_rejects_indirect_recursive_sequence() -> None:
    left: list[object] = []
    right: list[object] = [left]
    left.append(right)

    with pytest.raises(
        ValueError,
        match=r"recursive external binding value is not supported at value\[0\]\[0\]",
    ):
        value_to_ast(left)


def test_value_to_ast_rejects_recursive_dict() -> None:
    recursive: dict[object, object] = {}
    recursive["self"] = recursive

    with pytest.raises(
        ValueError,
        match=r"recursive external binding value is not supported at value\.values\[0\]",
    ):
        value_to_ast(recursive)


def test_value_to_ast_rejects_indirect_recursive_list_dict_cycle() -> None:
    left: list[object] = []
    right: dict[str, object] = {"loop": left}
    left.append(right)

    with pytest.raises(
        ValueError,
        match=r"recursive external binding value is not supported at value\[0\]\.values\[0\]",
    ):
        value_to_ast(left)


def test_validate_external_value_rejects_unsupported_values_without_conversion() -> None:
    with pytest.raises(
        ValueError,
        match=r"unsupported external binding value type at value: set",
    ):
        validate_external_value({"k"})
