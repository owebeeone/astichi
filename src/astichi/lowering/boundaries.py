"""Astichi boundary/value marker validation (issue 006).

This module owns the structural checks for the cross-scope identifier
surfaces:

- ``astichi_import(name)`` is the declaration-form surface. A bare
  ``astichi_import(...)`` statement is legal only in the contiguous
  top-of-body prefix of an Astichi scope (the module, or an
  ``@astichi_insert``-decorated class/def body).
- ``astichi_pass(name)`` is the value-form surface. It may appear where
  an expression is valid, but a bare statement-form ``astichi_pass(...)``
  is always rejected.

The interaction-matrix validator groups recognized markers by their
enclosing Astichi scope and rejects the forbidden combinations spelled
out in ``AstichiSingleSourceSummary.md §9.2``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from astichi.asttools import AstichiScope, AstichiScopeMap, is_astichi_insert_shell
from astichi.lowering.markers import RecognizedMarker
from astichi.lowering.sentinel_attrs import match_transparent_sentinel


_IMPORT_MARKER_NAMES: frozenset[str] = frozenset({"astichi_import"})
_PREFIX_NEUTRAL_MARKER_NAMES: frozenset[str] = frozenset({"astichi_pyimport"})


def validate_boundary_marker_placement(tree: ast.Module) -> None:
    """Enforce import-prefix placement and reject bare value-form pass."""
    errors: list[str] = []
    _validate_scope_body(tree.body, "module body", errors)
    if errors:
        raise ValueError("invalid Astichi boundary/value marker usage: " + "; ".join(errors))


def _validate_scope_body(
    body: list[ast.stmt], scope_label: str, errors: list[str]
) -> None:
    past_prefix = False
    for stmt in body:
        value_only = _top_level_value_only_marker(stmt)
        if value_only is not None:
            kind, lineno = value_only
            errors.append(
                f"{kind}(...) at line {lineno} in {scope_label}: {kind}(...) is "
                "value-form only and may not appear as a bare statement; bind it "
                "in a real expression (for example `x = astichi_pass(y)`) or use "
                "`astichi_import(name)` for declaration-style scope threading"
            )
            continue
        info = _top_level_import_marker(stmt)
        if info is not None:
            kind, lineno = info
            if past_prefix:
                errors.append(
                    f"{kind}(...) at line {lineno} in {scope_label}: "
                    f"boundary markers must form the top-of-body prefix, "
                    f"before any real statement"
                )
            # boundary-decl statement itself has no children worth
            # recursing into (its call arg is a bare `ast.Name`).
            continue
        if _top_level_prefix_neutral_marker(stmt) is not None:
            continue
        past_prefix = True
        _validate_nested(stmt, scope_label, errors)


def _validate_nested(
    node: ast.AST, scope_label: str, errors: list[str]
) -> None:
    """Walk a non-top-prefix statement for nested Astichi scopes.

    When we encounter an ``@astichi_insert`` shell we descend into its
    body as a fresh Astichi scope (its body has its own top-prefix
    rule). Bare statement-form ``astichi_pass(...)`` is rejected in any
    nested statement body, regardless of scope type.
    """
    if is_astichi_insert_shell(node):
        assert isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        for decorator in node.decorator_list:
            _flag_nested_boundaries(decorator, scope_label, errors)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _flag_nested_boundaries(node.args, scope_label, errors)
            if node.returns is not None:
                _flag_nested_boundaries(node.returns, scope_label, errors)
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                _flag_nested_boundaries(base, scope_label, errors)
            for keyword in node.keywords:
                _flag_nested_boundaries(keyword, scope_label, errors)
        _validate_scope_body(node.body, f"shell {node.name!r} body", errors)
        return
    _flag_nested_boundaries(node, scope_label, errors)


def _flag_nested_boundaries(
    node: ast.AST,
    scope_label: str,
    errors: list[str],
) -> None:
    """Descend into ``node`` for nested insert shells and bare pass statements."""
    if isinstance(node, ast.Expr):
        info = _top_level_value_only_marker(node)
        if info is not None:
            kind, lineno = info
            errors.append(
                f"{kind}(...) at line {lineno} in {scope_label}: {kind}(...) is "
                "value-form only and may not appear as a bare statement; bind it "
                "in a real expression (for example `x = astichi_pass(y)`) or use "
                "`astichi_import(name)` for declaration-style scope threading"
            )
            return
    if is_astichi_insert_shell(node):
        # Enter the shell as a fresh Astichi scope instead of treating
        # its contents as still inside `scope_label`.
        _validate_nested(node, scope_label, errors)
        return
    for child in ast.iter_child_nodes(node):
        _flag_nested_boundaries(child, scope_label, errors)


def _top_level_import_marker(stmt: ast.stmt) -> tuple[str, int] | None:
    """Return ``(marker_name, lineno)`` if ``stmt`` is a bare import call."""
    if not isinstance(stmt, ast.Expr):
        return None
    name = _import_expr_name(stmt.value)
    if name is None:
        return None
    lineno = getattr(stmt, "lineno", 0) or getattr(stmt.value, "lineno", 0) or 0
    return name, lineno


def _top_level_prefix_neutral_marker(stmt: ast.stmt) -> str | None:
    if not isinstance(stmt, ast.Expr):
        return None
    value = stmt.value
    if not isinstance(value, ast.Call):
        return None
    if not isinstance(value.func, ast.Name):
        return None
    if value.func.id not in _PREFIX_NEUTRAL_MARKER_NAMES:
        return None
    return value.func.id


def _boundary_call_name(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Name):
        return None
    if call.func.id not in _IMPORT_MARKER_NAMES:
        return None
    return call.func.id


def _import_expr_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return _boundary_call_name(node)
    return None


def _top_level_value_only_marker(stmt: ast.stmt) -> tuple[str, int] | None:
    if not isinstance(stmt, ast.Expr):
        return None
    name = _value_only_expr_name(stmt.value)
    if name is None:
        return None
    lineno = getattr(stmt, "lineno", 0) or getattr(stmt.value, "lineno", 0) or 0
    return name, lineno


def _value_only_expr_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and _is_pass_call(node):
        return "astichi_pass"
    sentinel = match_transparent_sentinel(
        node,
        is_marker_call=_is_pass_call,
    )
    if sentinel is None:
        return None
    return "astichi_pass"


def _is_pass_call(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Name)
        and call.func.id == "astichi_pass"
    )


# ---------------------------------------------------------------------------
# Astichi scope grouping (6b)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AstichiScopeKey:
    """Opaque scope identity for boundary / matrix validation.

    ``root_id`` is ``id(scope_root_node)`` — the module for the root
    scope, or an ``@astichi_insert`` shell node for a nested scope.
    Derived dicts key off this id and are stable within a single tree.
    """

    root_id: int
    label: str


@dataclass
class _ScopeMarkers:
    """Mutable accumulator of recognized markers per Astichi scope."""

    key: AstichiScopeKey
    imports: dict[str, int] = field(default_factory=dict)
    passes: dict[str, int] = field(default_factory=dict)
    keeps: dict[str, int] = field(default_factory=dict)
    args: dict[str, int] = field(default_factory=dict)
    exports: dict[str, int] = field(default_factory=dict)


def validate_boundary_interaction_matrix(
    tree: ast.Module, markers: tuple[RecognizedMarker, ...]
) -> None:
    """Reject forbidden boundary-marker combinations on the same name.

    Interaction matrix (issue 006 §9.2): within a single Astichi scope,
    ``astichi_import(name)`` cannot coexist with any of::

        astichi_pass(name)              # same-scope import + pass
        name__astichi_keep__            # import + keep suffix
        name__astichi_arg__             # import + arg suffix
        astichi_export(name)            # import + export

    Scope boundaries match `group_markers_by_astichi_scope`: the module
    body is the root Astichi scope, each ``@astichi_insert``-decorated
    class/def body is a fresh scope.
    """
    groups = group_markers_by_astichi_scope(tree, markers)
    errors: list[str] = []
    for bucket in groups.values():
        for import_name, import_lineno in bucket.imports.items():
            for other_kind, other_map, rendered in (
                ("astichi_pass", bucket.passes, "astichi_pass"),
                ("astichi_keep_identifier", bucket.keeps, "__astichi_keep__ suffix"),
                ("astichi_arg_identifier", bucket.args, "__astichi_arg__ suffix"),
                ("astichi_export", bucket.exports, "astichi_export"),
            ):
                other_lineno = other_map.get(import_name)
                if other_lineno is None:
                    continue
                errors.append(
                    f"astichi_import({import_name}) at line {import_lineno} "
                    f"conflicts with {rendered}({import_name}) at line "
                    f"{other_lineno} in {bucket.key.label}"
                )
    if errors:
        raise ValueError(
            "incompatible Astichi boundary-marker combinations: "
            + "; ".join(errors)
        )


def group_markers_by_astichi_scope(
    tree: ast.Module, markers: tuple[RecognizedMarker, ...]
) -> dict[int, _ScopeMarkers]:
    """Return a mapping ``scope_root_id -> _ScopeMarkers`` for interaction checks.

    A marker's *scope of belonging* is the innermost Astichi scope that
    contains its declaration site. Decorators and shell class/def names
    are visited in the **outer** scope (the scope that binds the name);
    only their bodies push a fresh scope. Expression-form
    ``astichi_insert`` payloads are fresh Astichi scopes under the shared
    `AstichiScopeMap`.
    """
    node_scope = _NodeScopeMap(tree)
    groups: dict[int, _ScopeMarkers] = {}
    groups[node_scope.root.root_id] = _ScopeMarkers(key=node_scope.root)

    for marker in markers:
        key = node_scope.scope_for(marker.node)
        bucket = groups.setdefault(key.root_id, _ScopeMarkers(key=key))
        name = marker.name_id
        if name is None:
            continue
        lineno = getattr(marker.node, "lineno", 0) or 0
        src = marker.source_name
        if src == "astichi_import" and marker.context.is_call_context():
            bucket.imports.setdefault(name, lineno)
        elif src == "astichi_pass" and marker.context.is_call_context():
            bucket.passes.setdefault(name, lineno)
        elif src == "astichi_keep_identifier":
            bucket.keeps.setdefault(name, lineno)
        elif src == "astichi_arg_identifier":
            bucket.args.setdefault(name, lineno)
        elif src == "astichi_export" and marker.context.is_call_context():
            bucket.exports.setdefault(name, lineno)
    return groups


class _NodeScopeMap:
    """Per-node Astichi-scope lookup (built once per tree)."""

    def __init__(self, tree: ast.Module) -> None:
        self._scope_map = AstichiScopeMap.from_tree(tree)
        self._keys_by_root_id: dict[int, AstichiScopeKey] = {}
        self.root = self._key_for(self._scope_map.root)

    def scope_for(self, node: ast.AST) -> AstichiScopeKey:
        return self._key_for(self._scope_map.scope_for(node))

    def _key_for(self, scope: AstichiScope) -> AstichiScopeKey:
        key = self._keys_by_root_id.get(scope.root_id)
        if key is None:
            key = AstichiScopeKey(root_id=scope.root_id, label=scope.label)
            self._keys_by_root_id[scope.root_id] = key
        return key
