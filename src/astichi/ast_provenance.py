"""AST source location (lineno / col_offset) propagation for synthetic nodes.

Astichi constructs many `ast.AST` nodes programmatically.  Those nodes must
inherit line/column information from the authored subtree they replace or from
an immediate surrounding node so diagnostics and downstream passes can anchor
errors without reading implementation code.

Policy:

- After building a fresh subtree, call :func:`propagate_ast_source_locations`
  with a *donor* that already carries a valid ``lineno`` (typically the hole,
  insert site, or a copied authored node).
- :func:`ast.fix_missing_locations` fills remaining gaps inside the subtree.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import TypeGuard

ASTICHI_SRC_FILE_ATTR = "_astichi_src_file"

# `ast.type_param` exists on Python 3.12+; omit when absent (e.g. older runtimes).
_located: list[type] = [
    ast.stmt,
    ast.expr,
    ast.excepthandler,
    ast.pattern,
]
if hasattr(ast, "type_param"):
    _located.append(ast.type_param)
_AST_LOCATION_TYPES: tuple[type, ...] = tuple(_located)


def requires_ast_source_location(node: ast.AST) -> bool:
    """Whether *node* should carry ``lineno`` for user-facing provenance."""
    return isinstance(node, _AST_LOCATION_TYPES)


def _lineno_ok(node: ast.AST) -> TypeGuard[ast.AST]:
    lo = getattr(node, "lineno", None)
    return isinstance(lo, int) and lo >= 1


def has_valid_ast_source_location(node: ast.AST) -> bool:
    """Return True if *node* has a usable ``lineno`` (and is a located kind)."""
    if not requires_ast_source_location(node):
        return True
    return _lineno_ok(node)


def iter_nodes_missing_ast_source_location(tree: ast.AST) -> Iterator[ast.AST]:
    """Yield located AST nodes that lack a valid ``lineno``."""
    for node in ast.walk(tree):
        if requires_ast_source_location(node) and not _lineno_ok(node):
            yield node


def first_ast_source_location_donor(tree: ast.AST) -> ast.AST | None:
    """Return the first node in *tree* that already has a valid ``lineno``."""
    for node in ast.walk(tree):
        if _lineno_ok(node):
            return node
    return None


def astichi_source_file(node: ast.AST) -> str | None:
    """Return Astichi's private source-file metadata for *node*, if present."""
    value = getattr(node, ASTICHI_SRC_FILE_ATTR, None)
    return value if isinstance(value, str) else None


def attach_astichi_source_file(tree: ast.AST, file_name: str) -> None:
    """Attach Astichi source-file metadata to every node in *tree*."""
    for node in ast.walk(tree):
        setattr(node, ASTICHI_SRC_FILE_ATTR, file_name)


def copy_astichi_location(target: ast.AST, source: ast.AST) -> ast.AST:
    """Copy Python and Astichi source location from *source* to *target*."""
    ast.copy_location(target, source)
    src_file = astichi_source_file(source)
    if src_file is not None:
        setattr(target, ASTICHI_SRC_FILE_ATTR, src_file)
    return target


def propagate_astichi_source_file(root: ast.AST, donor: ast.AST | None) -> None:
    """Fill missing Astichi source-file metadata on *root* from *donor*."""
    if donor is None:
        return
    src_file = astichi_source_file(donor)
    if src_file is None:
        return
    for node in ast.walk(root):
        if astichi_source_file(node) is None:
            setattr(node, ASTICHI_SRC_FILE_ATTR, src_file)


def propagate_ast_source_locations(root: ast.AST, donor: ast.AST | None) -> None:
    """Attach line/column info to *root* and its descendants.

    If *donor* has a valid ``lineno``, copy it onto *root* with
    :func:`ast.copy_location` (when supported), then run
    :func:`ast.fix_missing_locations` on *root*.

    If *donor* is missing or has no line, only :func:`ast.fix_missing_locations`
    runs (best-effort defaults — callers should prefer a real donor).
    """
    if isinstance(root, ast.Module):
        ast.fix_missing_locations(root)
        propagate_astichi_source_file(root, donor)
        return
    if donor is not None and _lineno_ok(donor):
        try:
            copy_astichi_location(root, donor)
        except (TypeError, ValueError):
            pass
    ast.fix_missing_locations(root)
    propagate_astichi_source_file(root, donor)


def assert_tree_has_ast_source_locations(tree: ast.AST) -> None:
    """Raise ``AssertionError`` if any located node lacks a valid ``lineno``."""
    missing = tuple(iter_nodes_missing_ast_source_location(tree))
    if missing:
        kinds = ", ".join(sorted({type(n).__name__ for n in missing}))
        raise AssertionError(
            f"{len(missing)} AST node(s) lack source location (lineno): {kinds}"
        )
