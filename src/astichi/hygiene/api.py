"""Name classification and hygiene support for Astichi V1."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from itertools import count
from typing import Literal

from astichi.lowering import RecognizedMarker
from astichi.model.basic import BasicComposable

Mode = Literal["strict", "permissive"]
LexicalRole = Literal["internal", "preserved", "external"]
BindingKind = Literal["binding", "reference"]


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
    scope_analysis: "ScopeAnalysis | None" = None


@dataclass(frozen=True)
class ScopeId:
    """Opaque scope identity for lexical-name hygiene."""

    serial: int


@dataclass(frozen=True)
class LexicalOccurrence:
    """A lexical identifier occurrence annotated with scope identity."""

    raw_name: str
    scope_id: ScopeId
    role: LexicalRole
    binding_kind: BindingKind
    ordinal: int
    node: ast.AST


@dataclass(frozen=True)
class ScopeAnalysis:
    """Scope-identity assignment for a lowered snippet."""

    occurrences: tuple[LexicalOccurrence, ...]


def analyze_names(
    composable: BasicComposable,
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
    composable: BasicComposable,
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


def assign_scope_identity(
    composable: BasicComposable,
    *,
    preserved_names: frozenset[str] = frozenset(),
    external_names: frozenset[str] = frozenset(),
    fresh_scope_nodes: tuple[ast.AST, ...] = (),
) -> ScopeAnalysis:
    """Assign scope identity to lexical name occurrences."""
    ignored_name_nodes = _ignored_name_nodes(composable.markers)
    marker_preserved_names = frozenset(
        marker.name_id
        for marker in composable.markers
        if marker.source_name == "astichi_keep" and marker.name_id is not None
    )
    marker_external_names = frozenset(
        marker.name_id
        for marker in composable.markers
        if marker.source_name == "astichi_bind_external" and marker.name_id is not None
    )
    effective_fresh_scope_nodes = fresh_scope_nodes + _marker_fresh_scope_nodes(
        composable.tree
    )
    fresh_scope_local_bindings: dict[int, frozenset[str]] = {}
    for node in effective_fresh_scope_nodes:
        if isinstance(node, ast.Call) and _is_expression_insert(node):
            fresh_scope_local_bindings[id(node)] = _collect_expression_bindings(
                node.args[1]
            )
    visitor = _ScopeIdentityVisitor(
        ignored_name_nodes=ignored_name_nodes,
        preserved_names=frozenset(set(preserved_names) | set(marker_preserved_names)),
        external_names=frozenset(set(external_names) | set(marker_external_names)),
        fresh_scope_nodes=effective_fresh_scope_nodes,
        fresh_scope_local_bindings=fresh_scope_local_bindings,
    )
    visitor.visit(composable.tree)
    return ScopeAnalysis(occurrences=tuple(visitor.occurrences))


def rename_scope_collisions(scope_analysis: ScopeAnalysis) -> None:
    """Rename colliding lexical names in-place based on scope identity."""
    grouped: dict[str, list[LexicalOccurrence]] = {}
    for occurrence in scope_analysis.occurrences:
        grouped.setdefault(occurrence.raw_name, []).append(occurrence)

    emitted_counter = count(1)
    for raw_name in sorted(grouped):
        occurrences = sorted(grouped[raw_name], key=lambda item: item.ordinal)
        by_scope: dict[int, list[LexicalOccurrence]] = {}
        for occurrence in occurrences:
            by_scope.setdefault(occurrence.scope_id.serial, []).append(occurrence)
        if len(by_scope) <= 1:
            continue
        ordered_scopes = sorted(
            by_scope.items(),
            key=lambda item: item[1][0].ordinal,
        )
        preserved_scopes = [
            scope_serial
            for scope_serial, scope_occurrences in ordered_scopes
            if any(
                occurrence.role == "preserved"
                for occurrence in scope_occurrences
            )
        ]
        keep_scope_serial = (
            preserved_scopes[0]
            if preserved_scopes
            else ordered_scopes[0][0]
        )
        for scope_serial, scope_occurrences in ordered_scopes:
            emitted_name = raw_name
            if scope_serial != keep_scope_serial:
                emitted_name = f"{raw_name}__astichi_scoped_{next(emitted_counter)}"
            for occurrence in scope_occurrences:
                if isinstance(occurrence.node, ast.Name):
                    occurrence.node.id = emitted_name
                elif isinstance(occurrence.node, ast.arg):
                    occurrence.node.arg = emitted_name


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


def _marker_fresh_scope_nodes(tree: ast.Module) -> tuple[ast.AST, ...]:
    collector = _FreshScopeCollector()
    collector.visit(tree)
    return tuple(collector.nodes)


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


class _FreshScopeCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.nodes: list[ast.AST] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if _has_insert_decorator(node.decorator_list):
            self.nodes.append(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if _has_insert_decorator(node.decorator_list):
            self.nodes.append(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if _has_insert_decorator(node.decorator_list):
            self.nodes.append(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_expression_insert(node):
            self.nodes.append(node)
        self.generic_visit(node)


def _has_insert_decorator(decorators: list[ast.expr]) -> bool:
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        if isinstance(decorator.func, ast.Name) and decorator.func.id == "astichi_insert":
            return True
    return False


def _is_expression_insert(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == "astichi_insert"
        and len(node.args) == 2
    )


def _collect_expression_bindings(node: ast.AST) -> frozenset[str]:
    """Collect Store-context names within an expression subtree."""
    bindings: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            bindings.add(child.id)
    return frozenset(bindings)


class _ScopeBindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings_by_scope: dict[int, frozenset[str]] = {}

    def visit_Module(self, node: ast.Module) -> None:
        self.bindings_by_scope[id(node)] = frozenset(self._collect_scope_bindings(node))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.bindings_by_scope[id(node)] = frozenset(self._collect_scope_bindings(node))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.bindings_by_scope[id(node)] = frozenset(self._collect_scope_bindings(node))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bindings_by_scope[id(node)] = frozenset(self._collect_scope_bindings(node))
        self.generic_visit(node)

    def _collect_scope_bindings(
        self,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> set[str]:
        collector = _SingleScopeBindingCollector()
        if isinstance(node, ast.Module):
            for statement in node.body:
                collector.visit(statement)
        else:
            for decorator in node.decorator_list:
                collector.visit(decorator)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for argument in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                    collector.bindings.add(argument.arg)
                if node.args.vararg is not None:
                    collector.bindings.add(node.args.vararg.arg)
                if node.args.kwarg is not None:
                    collector.bindings.add(node.args.kwarg.arg)
            for statement in node.body:
                collector.visit(statement)
        return collector.bindings


class _SingleScopeBindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bindings.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not node.name.endswith("__astichi__"):
            self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not node.name.endswith("__astichi__"):
            self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not node.name.endswith("__astichi__"):
            self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)


class _ScopeIdentityVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        ignored_name_nodes: set[int],
        preserved_names: frozenset[str],
        external_names: frozenset[str],
        fresh_scope_nodes: tuple[ast.AST, ...],
        fresh_scope_local_bindings: dict[int, frozenset[str]] | None = None,
    ) -> None:
        self.ignored_name_nodes = ignored_name_nodes
        self.preserved_names = preserved_names
        self.external_names = external_names
        self.fresh_scope_node_ids = {id(node) for node in fresh_scope_nodes}
        self.fresh_scope_local_bindings = fresh_scope_local_bindings or {}
        self.scope_counter = count(2)
        self.scope_stack: list[ScopeId] = [ScopeId(0), ScopeId(1)]
        self.astichi_scope_bindings_stack: list[frozenset[str] | None] = []
        self.python_bindings = _ScopeBindingCollector().bindings_by_scope
        self.python_scope_bindings: dict[int, frozenset[str]] = {}
        self.python_scope_stack: list[frozenset[str]] = []
        self.occurrences: list[LexicalOccurrence] = []
        self.ordinal_counter = count()

    def visit(self, node: ast.AST) -> object:
        if not self.python_scope_bindings:
            collector = _ScopeBindingCollector()
            collector.visit(node)
            self.python_scope_bindings = collector.bindings_by_scope
        return super().visit(node)

    def visit_Module(self, node: ast.Module) -> None:
        self._visit_python_scope(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_python_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_python_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_python_scope(node)

    def visit_Name(self, node: ast.Name) -> None:
        if id(node) in self.ignored_name_nodes:
            return
        if isinstance(node.ctx, ast.Load):
            role = self._load_role(node.id)
            binding_kind: BindingKind = "reference"
            scope_id = self._outer_scope() if role != "internal" else self._current_scope()
        else:
            role = "internal"
            binding_kind = "binding"
            scope_id = self._current_scope()
        self.occurrences.append(
            LexicalOccurrence(
                raw_name=node.id,
                scope_id=scope_id,
                role=role,
                binding_kind=binding_kind,
                ordinal=next(self.ordinal_counter),
                node=node,
            )
        )

    def visit_arg(self, node: ast.arg) -> None:
        self.occurrences.append(
            LexicalOccurrence(
                raw_name=node.arg,
                scope_id=self._current_scope(),
                role="internal",
                binding_kind="binding",
                ordinal=next(self.ordinal_counter),
                node=node,
            )
        )

    def _visit_python_scope(
        self,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> None:
        bindings = self.python_scope_bindings.get(id(node), frozenset())
        self.python_scope_stack.append(bindings)
        pushed_fresh = self._push_fresh_scope_if_needed(node)
        try:
            self.generic_visit(node)
        finally:
            if pushed_fresh:
                self.scope_stack.pop()
                self.astichi_scope_bindings_stack.pop()
            self.python_scope_stack.pop()

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            super().generic_visit(node)
            return
        pushed_fresh = self._push_fresh_scope_if_needed(node)
        try:
            super().generic_visit(node)
        finally:
            if pushed_fresh:
                self.scope_stack.pop()
                self.astichi_scope_bindings_stack.pop()

    def _push_fresh_scope_if_needed(self, node: ast.AST) -> bool:
        if id(node) not in self.fresh_scope_node_ids:
            return False
        self.scope_stack.append(ScopeId(next(self.scope_counter)))
        local = self.fresh_scope_local_bindings.get(id(node))
        self.astichi_scope_bindings_stack.append(local)
        return True

    def _current_scope(self) -> ScopeId:
        return self.scope_stack[-1]

    def _outer_scope(self) -> ScopeId:
        if len(self.scope_stack) >= 2:
            return self.scope_stack[-2]
        return self.scope_stack[-1]

    def _current_python_bindings(self) -> frozenset[str]:
        if not self.python_scope_stack:
            return frozenset()
        return self.python_scope_stack[-1]

    def _current_astichi_bindings(self) -> frozenset[str] | None:
        for local in reversed(self.astichi_scope_bindings_stack):
            if local is not None:
                return local
        return None

    def _load_role(self, raw_name: str) -> LexicalRole:
        astichi_local = self._current_astichi_bindings()
        if astichi_local is not None:
            if raw_name in astichi_local:
                return "internal"
        elif raw_name in self._current_python_bindings():
            return "internal"
        if raw_name in self.preserved_names:
            return "preserved"
        if raw_name in self.external_names:
            return "external"
        return "external"


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
