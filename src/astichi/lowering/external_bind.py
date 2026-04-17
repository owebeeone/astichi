"""Scope-aware substitution for astichi_bind_external."""

from __future__ import annotations

import ast
import copy
from contextlib import contextmanager
from typing import Iterator

from astichi.lowering.markers import recognize_markers
from astichi.model.external_values import value_to_ast


def apply_external_bindings(tree: ast.Module, bindings: dict[str, object]) -> None:
    """Remove satisfied bind markers and substitute bound reads in-place.

    The caller owns deep-copying when immutable composable state must be preserved.
    """

    if not bindings:
        return

    _reject_marker_argument_conflicts(tree, bindings)
    _reject_same_scope_rebinds(tree, bindings)

    _ExternalBindingTransformer(bindings).visit(tree)
    ast.fix_missing_locations(tree)


class _ExternalBindingTransformer(ast.NodeTransformer):
    def __init__(self, bindings: dict[str, object]) -> None:
        self.bindings = bindings
        self.binding_names = frozenset(bindings)
        self.shadow_stack: list[frozenset[str]] = [frozenset()]

    def visit_Module(self, node: ast.Module) -> ast.AST:
        node.body = self._visit_statements(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node.decorator_list = [self.visit(decorator) for decorator in node.decorator_list]
        node.args = self.visit(node.args)
        if node.returns is not None:
            node.returns = self.visit(node.returns)
        if hasattr(node, "type_params"):
            node.type_params = [self.visit(param) for param in node.type_params]
        with self._push_shadow(_function_scope_shadow_names(node, self.binding_names)):
            node.body = self._visit_statements(node.body)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        node.decorator_list = [self.visit(decorator) for decorator in node.decorator_list]
        node.args = self.visit(node.args)
        if node.returns is not None:
            node.returns = self.visit(node.returns)
        if hasattr(node, "type_params"):
            node.type_params = [self.visit(param) for param in node.type_params]
        with self._push_shadow(_function_scope_shadow_names(node, self.binding_names)):
            node.body = self._visit_statements(node.body)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        node.decorator_list = [self.visit(decorator) for decorator in node.decorator_list]
        node.bases = [self.visit(base) for base in node.bases]
        node.keywords = [self.visit(keyword) for keyword in node.keywords]
        if hasattr(node, "type_params"):
            node.type_params = [self.visit(param) for param in node.type_params]
        with self._push_shadow(_class_scope_shadow_names(node, self.binding_names)):
            node.body = self._visit_statements(node.body)
        return node

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        node.args = self.visit(node.args)
        shadowed = _argument_names(node.args) & self.binding_names
        with self._push_shadow(shadowed):
            node.body = self.visit(node.body)
        return node

    def visit_For(self, node: ast.For) -> ast.AST:
        node.iter = self.visit(node.iter)
        node.target = self.visit(node.target)
        shadowed = _target_names(node.target) & self.binding_names
        with self._push_shadow(shadowed):
            node.body = self._visit_statements(node.body)
            node.orelse = self._visit_statements(node.orelse)
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AST:
        node.iter = self.visit(node.iter)
        node.target = self.visit(node.target)
        shadowed = _target_names(node.target) & self.binding_names
        with self._push_shadow(shadowed):
            node.body = self._visit_statements(node.body)
            node.orelse = self._visit_statements(node.orelse)
        return node

    def visit_If(self, node: ast.If) -> ast.AST:
        node.test = self.visit(node.test)
        node.body = self._visit_statements(node.body)
        node.orelse = self._visit_statements(node.orelse)
        return node

    def visit_While(self, node: ast.While) -> ast.AST:
        node.test = self.visit(node.test)
        node.body = self._visit_statements(node.body)
        node.orelse = self._visit_statements(node.orelse)
        return node

    def visit_With(self, node: ast.With) -> ast.AST:
        node.items = [self.visit(item) for item in node.items]
        node.body = self._visit_statements(node.body)
        return node

    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.AST:
        node.items = [self.visit(item) for item in node.items]
        node.body = self._visit_statements(node.body)
        return node

    def visit_Try(self, node: ast.Try) -> ast.AST:
        node.body = self._visit_statements(node.body)
        node.handlers = [self.visit(handler) for handler in node.handlers]
        node.orelse = self._visit_statements(node.orelse)
        node.finalbody = self._visit_statements(node.finalbody)
        return node

    def visit_TryStar(self, node: ast.TryStar) -> ast.AST:
        node.body = self._visit_statements(node.body)
        node.handlers = [self.visit(handler) for handler in node.handlers]
        node.orelse = self._visit_statements(node.orelse)
        node.finalbody = self._visit_statements(node.finalbody)
        return node

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        if node.type is not None:
            node.type = self.visit(node.type)
        node.body = self._visit_statements(node.body)
        return node

    def visit_Match(self, node: ast.Match) -> ast.AST:
        node.subject = self.visit(node.subject)
        node.cases = [self.visit(case) for case in node.cases]
        return node

    def visit_match_case(self, node: ast.match_case) -> ast.match_case:
        if node.guard is not None:
            node.guard = self.visit(node.guard)
        node.body = self._visit_statements(node.body)
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.AST:
        added_shadow = self._visit_comprehension_generators(node.generators)
        with self._push_shadow(added_shadow):
            node.elt = self.visit(node.elt)
        return node

    def visit_SetComp(self, node: ast.SetComp) -> ast.AST:
        added_shadow = self._visit_comprehension_generators(node.generators)
        with self._push_shadow(added_shadow):
            node.elt = self.visit(node.elt)
        return node

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.AST:
        added_shadow = self._visit_comprehension_generators(node.generators)
        with self._push_shadow(added_shadow):
            node.elt = self.visit(node.elt)
        return node

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        added_shadow = self._visit_comprehension_generators(node.generators)
        with self._push_shadow(added_shadow):
            node.key = self.visit(node.key)
            node.value = self.visit(node.value)
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if not isinstance(node.ctx, ast.Load):
            return node
        if node.id not in self.bindings:
            return node
        if node.id in self._current_shadow():
            return node
        return value_to_ast(self.bindings[node.id])

    def _visit_statements(self, statements: list[ast.stmt]) -> list[ast.stmt]:
        visited: list[ast.stmt] = []
        for statement in statements:
            if _is_matching_bind_external_expr(statement, self.bindings):
                continue
            transformed = self.visit(statement)
            if transformed is None:
                continue
            if isinstance(transformed, list):
                visited.extend(transformed)
            else:
                assert isinstance(transformed, ast.stmt)
                visited.append(transformed)
        return visited

    def _visit_comprehension_generators(
        self,
        generators: list[ast.comprehension],
    ) -> frozenset[str]:
        accumulated_shadow: set[str] = set()
        for generator in generators:
            with self._push_shadow(accumulated_shadow):
                generator.iter = self.visit(generator.iter)
                generator.target = self.visit(generator.target)
            shadowed = _target_names(generator.target) & self.binding_names
            accumulated_shadow.update(shadowed)
            with self._push_shadow(accumulated_shadow):
                generator.ifs = [self.visit(condition) for condition in generator.ifs]
        return frozenset(accumulated_shadow)

    def _current_shadow(self) -> frozenset[str]:
        return self.shadow_stack[-1]

    @contextmanager
    def _push_shadow(self, shadowed: frozenset[str] | set[str]) -> Iterator[None]:
        if not shadowed:
            yield
            return
        combined = frozenset(set(self._current_shadow()) | set(shadowed))
        self.shadow_stack.append(combined)
        try:
            yield
        finally:
            self.shadow_stack.pop()


def _reject_marker_argument_conflicts(tree: ast.Module, bindings: dict[str, object]) -> None:
    for marker in recognize_markers(tree):
        if marker.name_id is None or marker.name_id not in bindings:
            continue
        if marker.source_name == "astichi_bind_external":
            continue
        line = getattr(marker.node, "lineno", "?")
        raise ValueError(
            f"external binding `{marker.name_id}` collides with a name-bearing marker "
            f"identifier at line {line} ({marker.source_name})"
        )


def _reject_same_scope_rebinds(tree: ast.Module, bindings: dict[str, object]) -> None:
    checker = _SameScopeRebindChecker(frozenset(bindings))
    checker.visit(tree)


class _SameScopeRebindChecker(ast.NodeVisitor):
    def __init__(self, binding_names: frozenset[str]) -> None:
        self.binding_names = binding_names

    def visit_Module(self, node: ast.Module) -> None:
        self._check_scope(node.body, frozenset())
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_scope(node.body, _argument_names(node.args))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_scope(node.body, _argument_names(node.args))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._check_scope(node.body, frozenset())
        self.generic_visit(node)

    def _check_scope(
        self,
        body: list[ast.stmt],
        parameter_names: frozenset[str],
    ) -> None:
        declared_externals = _direct_bind_external_names(body) & self.binding_names
        if not declared_externals:
            return
        same_scope_bindings = parameter_names | _collect_same_scope_bindings(body)
        for name in sorted(declared_externals & same_scope_bindings):
            raise ValueError(f"same-scope rebind of externally bound name `{name}`")


def _direct_bind_external_names(body: list[ast.stmt]) -> frozenset[str]:
    collector = _DirectBindExternalCollector()
    for statement in body:
        collector.visit(statement)
    return frozenset(collector.names)


class _DirectBindExternalCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Expr(self, node: ast.Expr) -> None:
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "astichi_bind_external"
            and node.value.args
            and isinstance(node.value.args[0], ast.Name)
        ):
            self.names.add(node.value.args[0].id)
            return
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        if node.returns is not None:
            self.visit(node.returns)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        if node.returns is not None:
            self.visit(node.returns)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_ListComp(self, node: ast.ListComp) -> None:
        return

    def visit_SetComp(self, node: ast.SetComp) -> None:
        return

    def visit_DictComp(self, node: ast.DictComp) -> None:
        return

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        return


class _SameScopeBindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bindings.add(node.id)

    def visit_arg(self, node: ast.arg) -> None:
        self.bindings.add(node.arg)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.target)
        self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.target)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        if node.annotation is not None:
            self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        for statement in node.body:
            self.visit(statement)
        for statement in node.orelse:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit(node.iter)
        for statement in node.body:
            self.visit(statement)
        for statement in node.orelse:
            self.visit(statement)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        return

    def visit_SetComp(self, node: ast.SetComp) -> None:
        return

    def visit_DictComp(self, node: ast.DictComp) -> None:
        return

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        if node.returns is not None:
            self.visit(node.returns)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        if node.returns is not None:
            self.visit(node.returns)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.bindings.add(alias.asname or alias.name)


def _collect_same_scope_bindings(body: list[ast.stmt]) -> frozenset[str]:
    collector = _SameScopeBindingCollector()
    for statement in body:
        collector.visit(statement)
    return frozenset(collector.bindings)


def _function_scope_shadow_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    binding_names: frozenset[str],
) -> frozenset[str]:
    scope_bindings = set(_argument_names(node.args))
    scope_bindings.update(_collect_same_scope_bindings(node.body))
    return frozenset(scope_bindings & binding_names)


def _class_scope_shadow_names(
    node: ast.ClassDef,
    binding_names: frozenset[str],
) -> frozenset[str]:
    return frozenset(_collect_same_scope_bindings(node.body) & binding_names)


def _argument_names(node: ast.arguments) -> frozenset[str]:
    names: set[str] = set()
    for argument in node.posonlyargs + node.args + node.kwonlyargs:
        names.add(argument.arg)
    if node.vararg is not None:
        names.add(node.vararg.arg)
    if node.kwarg is not None:
        names.add(node.kwarg.arg)
    return frozenset(names)


def _target_names(node: ast.AST) -> frozenset[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.add(child.id)
    return frozenset(names)


def _is_matching_bind_external_expr(node: ast.stmt, bindings: dict[str, object]) -> bool:
    if not isinstance(node, ast.Expr):
        return False
    if not isinstance(node.value, ast.Call):
        return False
    if not isinstance(node.value.func, ast.Name):
        return False
    if node.value.func.id != "astichi_bind_external":
        return False
    if not node.value.args:
        return False
    first_arg = node.value.args[0]
    return isinstance(first_arg, ast.Name) and first_arg.id in bindings
