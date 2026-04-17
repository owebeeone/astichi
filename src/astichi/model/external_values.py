"""External bind value validation and AST conversion."""

from __future__ import annotations

import ast

MAX_EXTERNAL_VALUE_DEPTH = 32


def validate_external_value(value: object) -> None:
    """Validate that a Python value is supported by the V2 bind policy."""

    _convert_external_value(value, depth=0, path="value", active_ids=set())


def value_to_ast(value: object) -> ast.expr:
    """Convert a supported Python value into an expression AST node."""

    return _convert_external_value(value, depth=0, path="value", active_ids=set())


def _convert_external_value(
    value: object,
    *,
    depth: int,
    path: str,
    active_ids: set[int],
) -> ast.expr:
    if depth > MAX_EXTERNAL_VALUE_DEPTH:
        raise ValueError(
            f"external binding value exceeds max depth {MAX_EXTERNAL_VALUE_DEPTH} at {path}"
        )

    if value is None:
        return ast.Constant(value=None)
    if isinstance(value, bool):
        return ast.Constant(value=value)
    if isinstance(value, int):
        return ast.Constant(value=value)
    if isinstance(value, float):
        return ast.Constant(value=value)
    if isinstance(value, str):
        return ast.Constant(value=value)
    if isinstance(value, tuple):
        return ast.Tuple(
            elts=_convert_sequence_elements(
                value,
                depth=depth,
                path=path,
                active_ids=active_ids,
            ),
            ctx=ast.Load(),
        )
    if isinstance(value, list):
        return ast.List(
            elts=_convert_sequence_elements(
                value,
                depth=depth,
                path=path,
                active_ids=active_ids,
            ),
            ctx=ast.Load(),
        )

    raise ValueError(f"unsupported external binding value type at {path}: {type(value).__name__}")


def _convert_sequence_elements(
    value: tuple[object, ...] | list[object],
    *,
    depth: int,
    path: str,
    active_ids: set[int],
) -> list[ast.expr]:
    object_id = id(value)
    if object_id in active_ids:
        raise ValueError(f"recursive external binding value is not supported at {path}")

    active_ids.add(object_id)
    try:
        return [
            _convert_external_value(
                item,
                depth=depth + 1,
                path=f"{path}[{index}]",
                active_ids=active_ids,
            )
            for index, item in enumerate(value)
        ]
    finally:
        active_ids.remove(object_id)
