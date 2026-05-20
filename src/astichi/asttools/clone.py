"""Fast cloning helpers for Python AST trees."""

from __future__ import annotations

import ast
from typing import TypeVar, cast

T = TypeVar("T")


def clone_ast(value: T) -> T:
    """Clone AST nodes and AST containers without ``copy.deepcopy``'s memo.

    Astichi treats Python AST values as owned trees. The generic deepcopy
    algorithm pays for cycle and shared-object preservation that these trees do
    not need on hot materialization paths.
    """
    return cast(T, _clone_value(value))


def _clone_value(value: object) -> object:
    if isinstance(value, ast.AST):
        return _clone_node(value)
    if isinstance(value, list):
        return [_clone_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clone_value(item) for item in value)
    return value


def _clone_node(node: ast.AST) -> ast.AST:
    cloned = type(node).__new__(type(node))
    field_names = getattr(node, "_fields", ())
    location_attrs = getattr(node, "_attributes", ())
    node_dict = getattr(node, "__dict__", {})

    for field_name in field_names:
        if field_name in node_dict:
            setattr(cloned, field_name, _clone_value(node_dict[field_name]))
        elif hasattr(node, field_name):
            setattr(cloned, field_name, _clone_value(getattr(node, field_name)))

    for attr_name in location_attrs:
        if attr_name in node_dict:
            setattr(cloned, attr_name, node_dict[attr_name])
        elif hasattr(node, attr_name):
            setattr(cloned, attr_name, getattr(node, attr_name))

    skipped_names = field_names + location_attrs
    for attr_name, attr_value in node_dict.items():
        if attr_name in skipped_names:
            continue
        setattr(cloned, attr_name, _clone_value(attr_value))

    return cloned
