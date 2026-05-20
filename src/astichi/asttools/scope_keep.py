"""Internal scope metadata for synthetic keep declarations."""

from __future__ import annotations

import ast
from collections.abc import Iterable

ASTICHI_SCOPE_KEEP_NAMES_ATTR = "_astichi_scope_keep_names"


def add_astichi_scope_keep_names(node: ast.AST, names: Iterable[str]) -> None:
    """Attach synthetic keep declarations to an Astichi scope node."""
    new_names = frozenset(names)
    if not new_names:
        return
    existing = astichi_scope_keep_names(node)
    setattr(node, ASTICHI_SCOPE_KEEP_NAMES_ATTR, existing | new_names)


def astichi_scope_keep_names(node: ast.AST) -> frozenset[str]:
    """Return synthetic keep declarations attached to *node*."""
    value = getattr(node, ASTICHI_SCOPE_KEEP_NAMES_ATTR, None)
    if value is None:
        return frozenset()
    if isinstance(value, frozenset) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, (set, tuple, list)) and all(
        isinstance(item, str) for item in value
    ):
        return frozenset(value)
    return frozenset()
