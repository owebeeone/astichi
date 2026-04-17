"""Astichi scope-boundary marker validation (issue 006).

This module owns the *structural* checks for the two cross-scope
boundary markers:

- ``astichi_import(name)``: imports an outer-scope identifier into the
  immediately enclosing Astichi scope.
- ``astichi_pass(name)``: exposes an inner-scope identifier to the
  immediately enclosing outer Astichi scope.

Both are **declarations**, not executable calls. The author of a piece
must place them as the contiguous top-of-body prefix of their Astichi
scope (the module, or an ``@astichi_insert``-decorated class/def body).
The placement rule is enforced at ``compile()`` time so users see the
error eagerly.

The interaction-matrix validator (issue 006 6b) groups recognized
markers by their enclosing Astichi scope and rejects the forbidden
combinations spelled out in
``AstichiSingleSourceSummary.md §9.2``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from astichi.lowering.markers import RecognizedMarker


_BOUNDARY_MARKER_NAMES: frozenset[str] = frozenset({"astichi_import", "astichi_pass"})


def validate_boundary_marker_placement(tree: ast.Module) -> None:
    """Reject misplaced ``astichi_import`` / ``astichi_pass`` markers.

    Placement rule (issue 006 §9.2):

    - A boundary marker must appear as a bare expression-statement in
      the immediately enclosing Astichi scope body.
    - All boundary markers in a scope must form the contiguous top
      prefix of that body (no real statement may precede any of them).
    - Boundary markers may not be nested inside non-Astichi compound
      structures (``if``, ``for``, ``try``, non-shell ``def``/``class``,
      expressions, decorators, ...); those positions do not correspond
      to an Astichi scope at all.

    An Astichi scope body is either the module body or the body of an
    ``@astichi_insert``-decorated ``FunctionDef`` / ``AsyncFunctionDef``
    / ``ClassDef``. Expression-form ``astichi_insert(name, expr)`` has
    no body.
    """
    errors: list[str] = []
    _validate_scope_body(tree.body, "module body", errors)
    if errors:
        raise ValueError(
            "misplaced Astichi boundary marker(s): " + "; ".join(errors)
        )


def _validate_scope_body(
    body: list[ast.stmt], scope_label: str, errors: list[str]
) -> None:
    past_prefix = False
    for stmt in body:
        info = _top_level_boundary_marker(stmt)
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
        past_prefix = True
        _validate_nested(stmt, scope_label, errors)


def _validate_nested(
    node: ast.AST, scope_label: str, errors: list[str]
) -> None:
    """Walk a non-top-prefix statement, flagging any nested boundary call.

    When we encounter an ``@astichi_insert`` shell we descend into its
    body as a fresh Astichi scope (its body has its own top-prefix
    rule). Decorators / arguments / bases of the shell still belong to
    the outer ``scope_label``; any boundary call there is misplaced.
    """
    if _is_insert_shell(node):
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
    node: ast.AST, scope_label: str, errors: list[str]
) -> None:
    """Flag every boundary call inside ``node``, descending into shells as scopes."""
    if isinstance(node, ast.Call):
        kind = _boundary_call_name(node)
        if kind is not None:
            lineno = getattr(node, "lineno", 0) or 0
            errors.append(
                f"{kind}(...) at line {lineno}: must appear at the top of "
                f"the immediately enclosing Astichi scope body "
                f"({scope_label}); nested or non-statement positions are "
                f"rejected"
            )
            # Fall through and still recurse into args in case of
            # degenerate nesting like `astichi_import(astichi_pass(x))`.
    if _is_insert_shell(node):
        # Enter the shell as a fresh Astichi scope instead of treating
        # its contents as still inside `scope_label`.
        _validate_nested(node, scope_label, errors)
        return
    for child in ast.iter_child_nodes(node):
        _flag_nested_boundaries(child, scope_label, errors)


def _top_level_boundary_marker(stmt: ast.stmt) -> tuple[str, int] | None:
    """Return ``(marker_name, lineno)`` if ``stmt`` is a bare boundary call."""
    if not isinstance(stmt, ast.Expr):
        return None
    if not isinstance(stmt.value, ast.Call):
        return None
    name = _boundary_call_name(stmt.value)
    if name is None:
        return None
    lineno = getattr(stmt, "lineno", 0) or getattr(stmt.value, "lineno", 0) or 0
    return name, lineno


def _boundary_call_name(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Name):
        return None
    if call.func.id not in _BOUNDARY_MARKER_NAMES:
        return None
    return call.func.id


def _is_insert_shell(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if isinstance(decorator.func, ast.Name) and decorator.func.id == "astichi_insert":
            return True
    return False


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

    ``astichi_pass`` may freely coexist with keep / arg / export —
    supplying a name outward does not conflict with hygiene pins or
    export-side supplies on the same name.

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
    ``astichi_insert`` has no body and therefore never pushes a scope.
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
        if src == "astichi_import" and marker.context == "call":
            bucket.imports.setdefault(name, lineno)
        elif src == "astichi_pass" and marker.context == "call":
            bucket.passes.setdefault(name, lineno)
        elif src == "astichi_keep_identifier":
            bucket.keeps.setdefault(name, lineno)
        elif src == "astichi_arg_identifier":
            bucket.args.setdefault(name, lineno)
        elif src == "astichi_export" and marker.context == "call":
            bucket.exports.setdefault(name, lineno)
    return groups


class _NodeScopeMap:
    """Per-node Astichi-scope lookup (built once per tree)."""

    def __init__(self, tree: ast.Module) -> None:
        self.root = AstichiScopeKey(root_id=id(tree), label="module body")
        self._by_id: dict[int, AstichiScopeKey] = {}
        self._walk(tree, self.root)

    def scope_for(self, node: ast.AST) -> AstichiScopeKey:
        return self._by_id.get(id(node), self.root)

    def _walk(self, node: ast.AST, scope: AstichiScopeKey) -> None:
        self._by_id[id(node)] = scope
        if isinstance(node, ast.Module):
            for child in node.body:
                self._walk(child, scope)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # The def/class itself and its decorators live in the outer
            # `scope`; its body (and its arguments, for defs) live in
            # the inner scope when this is a shell.
            for decorator in node.decorator_list:
                self._walk(decorator, scope)
            body_scope = scope
            if _is_insert_shell(node):
                body_scope = AstichiScopeKey(
                    root_id=id(node), label=f"shell {node.name!r} body"
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._walk_arguments(node.args, body_scope)
                if node.returns is not None:
                    self._walk(node.returns, scope)
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    self._walk(base, scope)
                for keyword in node.keywords:
                    self._walk(keyword, scope)
            for child in node.body:
                self._walk(child, body_scope)
            return
        for child in ast.iter_child_nodes(node):
            self._walk(child, scope)

    def _walk_arguments(self, args: ast.arguments, scope: AstichiScopeKey) -> None:
        for argument in (
            list(args.posonlyargs)
            + list(args.args)
            + list(args.kwonlyargs)
        ):
            self._walk(argument, scope)
        if args.vararg is not None:
            self._walk(args.vararg, scope)
        if args.kwarg is not None:
            self._walk(args.kwarg, scope)
        for default in args.defaults + args.kw_defaults:
            if default is not None:
                self._walk(default, scope)
