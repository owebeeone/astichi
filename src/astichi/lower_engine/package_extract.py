"""Python extraction helpers for lower template package rows."""

from __future__ import annotations

import ast
from collections.abc import Iterable

from astichi.asttools import import_statement_binding_names
from astichi.lower_engine.templates import TemplateScopeSpec


def extract_scope_specs(tree: ast.Module) -> tuple[TemplateScopeSpec, ...]:
    """Extract deterministic lexical scope specs from a Python module AST."""
    scopes: list[TemplateScopeSpec] = []

    def append_scope(
        *,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        scope_kind: str,
        ast_path: str,
        owner_path: tuple[str, ...],
        parent_scope_id: int | None,
    ) -> int:
        arguments = _argument_names(node)
        scope_id = len(scopes)
        scopes.append(
            TemplateScopeSpec(
                scope_kind=scope_kind,
                ast_path=ast_path,
                owner_path=owner_path,
                local_bindings=tuple(sorted(_scope_binding_names(node))),
                arguments=tuple(sorted(arguments)),
                parent_scope_id=parent_scope_id,
            )
        )
        return scope_id

    def visit(
        node: ast.AST,
        *,
        ast_path: str,
        owner_path: tuple[str, ...],
        parent_scope_id: int | None,
    ) -> None:
        scope_id = parent_scope_id
        child_owner_path = owner_path
        if isinstance(node, ast.Module):
            scope_id = append_scope(
                node=node,
                scope_kind="module",
                ast_path=ast_path,
                owner_path=owner_path,
                parent_scope_id=None,
            )
        elif isinstance(node, ast.AsyncFunctionDef):
            child_owner_path = (*owner_path, node.name)
            scope_id = append_scope(
                node=node,
                scope_kind="async_function",
                ast_path=ast_path,
                owner_path=child_owner_path,
                parent_scope_id=parent_scope_id,
            )
        elif isinstance(node, ast.FunctionDef):
            child_owner_path = (*owner_path, node.name)
            scope_id = append_scope(
                node=node,
                scope_kind="function",
                ast_path=ast_path,
                owner_path=child_owner_path,
                parent_scope_id=parent_scope_id,
            )
        elif isinstance(node, ast.ClassDef):
            child_owner_path = (*owner_path, node.name)
            scope_id = append_scope(
                node=node,
                scope_kind="class",
                ast_path=ast_path,
                owner_path=child_owner_path,
                parent_scope_id=parent_scope_id,
            )

        for field_name, value in ast.iter_fields(node):
            for child_path, child in _iter_ast_children(
                field_name=field_name,
                value=value,
                parent_path=ast_path,
            ):
                visit(
                    child,
                    ast_path=child_path,
                    owner_path=child_owner_path,
                    parent_scope_id=scope_id,
                )

    visit(
        tree,
        ast_path="",
        owner_path=(),
        parent_scope_id=None,
    )
    return tuple(scopes)


def _iter_ast_children(
    *,
    field_name: str,
    value: object,
    parent_path: str,
) -> Iterable[tuple[str, ast.AST]]:
    if isinstance(value, ast.AST):
        yield _join_ast_path(parent_path, field_name), value
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, ast.AST):
                yield _join_ast_path(parent_path, f"{field_name}[{index}]"), child


def _join_ast_path(parent_path: str, part: str) -> str:
    if parent_path == "":
        return part
    return f"{parent_path}/{part}"


def _scope_binding_names(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> frozenset[str]:
    names: set[str] = set(_argument_names(scope))

    class Collector(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            names.add(node.name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            names.add(node.name)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            names.add(node.name)

        def visit_Import(self, node: ast.Import) -> None:
            names.update(import_statement_binding_names(node, include_star=True))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            names.update(import_statement_binding_names(node, include_star=True))

    collector = Collector()
    for statement in scope.body:
        collector.visit(statement)
    return frozenset(names)


def _argument_names(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> frozenset[str]:
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return frozenset()
    names = {
        argument.arg
        for argument in (
            list(scope.args.posonlyargs)
            + list(scope.args.args)
            + list(scope.args.kwonlyargs)
        )
    }
    if scope.args.vararg is not None:
        names.add(scope.args.vararg.arg)
    if scope.args.kwarg is not None:
        names.add(scope.args.kwarg.arg)
    return frozenset(names)
