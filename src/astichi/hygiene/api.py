"""Name classification and hygiene support for Astichi V1."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Literal

from astichi.frontend.compiled import FrontendComposable
from astichi.lowering import RecognizedMarker

Mode = Literal["strict", "permissive"]


@dataclass(frozen=True)
class ImpliedDemand:
    """An unresolved free identifier promoted to a demand."""

    name: str


@dataclass(frozen=True)
class NameClassification:
    """Classification result for names in a lowered snippet."""

    locals: frozenset[str]
    kept: frozenset[str]
    preserved: frozenset[str]
    externals: frozenset[str]
    unresolved_free: frozenset[str]
    implied_demands: tuple[ImpliedDemand, ...]


@dataclass(frozen=True)
class HygieneResult:
    """Hygiene result for a frontend composable."""

    classification: NameClassification
    tree: ast.Module


def analyze_names(
    composable: FrontendComposable,
    *,
    mode: Mode = "strict",
    preserved_names: frozenset[str] = frozenset(),
) -> NameClassification:
    """Classify names for a frontend composable."""
    if mode not in ("strict", "permissive"):
        raise ValueError(f"unsupported hygiene mode: {mode}")

    ignored_name_nodes = _ignored_name_nodes(composable.markers)
    local_bindings = _collect_local_bindings(composable.tree)
    kept = frozenset(
        marker.name_id
        for marker in composable.markers
        if marker.source_name == "astichi_keep" and marker.name_id is not None
    )
    externals = frozenset(
        marker.name_id
        for marker in composable.markers
        if marker.source_name == "astichi_bind_external" and marker.name_id is not None
    )
    preserved = frozenset(set(kept) | set(preserved_names))

    unresolved: set[str] = set()
    for node in ast.walk(composable.tree):
        if not isinstance(node, ast.Name):
            continue
        if id(node) in ignored_name_nodes:
            continue
        if not isinstance(node.ctx, ast.Load):
            continue
        if node.id in local_bindings:
            continue
        if node.id in preserved:
            continue
        if node.id in externals:
            continue
        unresolved.add(node.id)

    unresolved_free = frozenset(sorted(unresolved))
    implied_demands: tuple[ImpliedDemand, ...]
    if mode == "permissive":
        implied_demands = tuple(ImpliedDemand(name=name) for name in sorted(unresolved))
    else:
        if unresolved:
            names = ", ".join(sorted(unresolved))
            raise ValueError(f"unresolved free identifiers in strict mode: {names}")
        implied_demands = ()

    return NameClassification(
        locals=frozenset(sorted(local_bindings)),
        kept=frozenset(sorted(kept)),
        preserved=frozenset(sorted(preserved)),
        externals=frozenset(sorted(externals)),
        unresolved_free=unresolved_free,
        implied_demands=implied_demands,
    )


def rewrite_hygienically(
    composable: FrontendComposable,
    *,
    preserved_names: frozenset[str] = frozenset(),
    mode: Mode = "strict",
) -> HygieneResult:
    """Rewrite colliding local names hygienically."""
    classification = analyze_names(
        composable,
        mode=mode,
        preserved_names=preserved_names,
    )
    renamer = _Renamer(classification.preserved)
    rewritten = renamer.visit(ast.fix_missing_locations(ast.parse(ast.unparse(composable.tree))))
    assert isinstance(rewritten, ast.Module)
    return HygieneResult(
        classification=classification,
        tree=rewritten,
    )


def _ignored_name_nodes(markers: tuple[object, ...]) -> set[int]:
    ignored: set[int] = set()
    for marker in markers:
        if not isinstance(marker, RecognizedMarker):
            continue
        if isinstance(marker.node, ast.Call):
            if isinstance(marker.node.func, ast.Name):
                ignored.add(id(marker.node.func))
            if marker.spec.is_name_bearing():
                first_arg = marker.node.args[0]
                if isinstance(first_arg, ast.Name):
                    ignored.add(id(first_arg))
    return ignored


def _collect_local_bindings(tree: ast.Module) -> set[str]:
    collector = _BindingCollector()
    collector.visit(tree)
    return collector.bindings


class _BindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bindings.add(node.id)

    def visit_arg(self, node: ast.arg) -> None:
        self.bindings.add(node.arg)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not node.name.endswith("__astichi__"):
            self.bindings.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not node.name.endswith("__astichi__"):
            self.bindings.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not node.name.endswith("__astichi__"):
            self.bindings.add(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name)


class _Renamer(ast.NodeTransformer):
    def __init__(self, preserved: frozenset[str]) -> None:
        self._preserved = preserved
        self._counter = 0
        self._scopes: list[dict[str, str]] = []

    def visit_Module(self, node: ast.Module) -> ast.AST:
        return self._visit_scope(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name in self._preserved:
            node.name = self._fresh(node.name)
        return self._visit_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        if node.name in self._preserved:
            node.name = self._fresh(node.name)
        return self._visit_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        if node.name in self._preserved:
            node.name = self._fresh(node.name)
        return self._visit_scope(node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        if node.arg in self._preserved:
            replacement = self._fresh(node.arg)
            self._current_scope()[node.arg] = replacement
            node.arg = replacement
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, (ast.Store, ast.Del)) and node.id in self._preserved:
            replacement = self._scope_lookup(node.id)
            if replacement is None:
                replacement = self._fresh(node.id)
                self._current_scope()[node.id] = replacement
            node.id = replacement
            return node

        replacement = self._scope_lookup(node.id)
        if replacement is not None:
            node.id = replacement
        return node

    def _visit_scope(
        self,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> ast.AST:
        self._scopes.append({})
        try:
            return self.generic_visit(node)
        finally:
            self._scopes.pop()

    def _current_scope(self) -> dict[str, str]:
        return self._scopes[-1]

    def _scope_lookup(self, name: str) -> str | None:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return None

    def _fresh(self, name: str) -> str:
        self._counter += 1
        return f"__astichi_local_{name}_{self._counter}"
