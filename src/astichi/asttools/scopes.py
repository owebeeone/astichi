"""Astichi owner-scope mapping helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from astichi.asttools.inserts import (
    is_astichi_insert_shell,
    is_expression_insert_call,
)


@dataclass(eq=False)
class AstichiScope:
    """Astichi owner-scope identity for one AST owner root."""

    root: ast.AST
    label: str
    parent: "AstichiScope | None" = None
    _node_ids: set[int] = field(default_factory=set, repr=False, compare=False)

    @property
    def root_id(self) -> int:
        return id(self.root)

    def owns(self, node: ast.AST) -> bool:
        return id(node) in self._node_ids

    def is_root(self, node: ast.AST) -> bool:
        return id(node) == self.root_id


class AstichiScopeMap:
    """Per-node Astichi owner-scope lookup."""

    def __init__(self, tree: ast.Module) -> None:
        self.root = AstichiScope(root=tree, label="module body", parent=None)
        self._by_id: dict[int, AstichiScope] = {}
        self._nested_python_root_by_id: dict[int, ast.AST] = {}
        self._walk(tree, self.root, nested_python_root=None)

    @classmethod
    def from_tree(cls, tree: ast.Module) -> "AstichiScopeMap":
        return cls(tree)

    def scope_for(self, node: ast.AST) -> AstichiScope:
        return self._by_id.get(id(node), self.root)

    def parent_scope_for(self, scope: AstichiScope) -> AstichiScope | None:
        return scope.parent

    def nested_python_root_for(self, node: ast.AST) -> ast.AST | None:
        return self._nested_python_root_by_id.get(id(node))

    def _record(
        self,
        node: ast.AST,
        scope: AstichiScope,
        *,
        nested_python_root: ast.AST | None,
    ) -> None:
        self._by_id[id(node)] = scope
        scope._node_ids.add(id(node))
        if nested_python_root is not None:
            self._nested_python_root_by_id[id(node)] = nested_python_root

    def _walk(
        self,
        node: ast.AST,
        scope: AstichiScope,
        *,
        nested_python_root: ast.AST | None,
    ) -> None:
        self._record(node, scope, nested_python_root=nested_python_root)
        if isinstance(node, ast.Module):
            for child in node.body:
                self._walk(child, scope, nested_python_root=None)
            return
        if is_expression_insert_call(node):
            # Intentional ownership widening over the historical boundary-only
            # mapper: expression-insert payloads are Astichi scopes too.
            self._walk(node.func, scope, nested_python_root=nested_python_root)
            self._walk(node.args[0], scope, nested_python_root=nested_python_root)
            payload_scope = AstichiScope(
                root=node,
                label="expression insert payload",
                parent=scope,
            )
            self._walk(node.args[1], payload_scope, nested_python_root=None)
            for keyword in node.keywords:
                self._walk(keyword, scope, nested_python_root=nested_python_root)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            is_shell = is_astichi_insert_shell(node)
            body_scope = scope
            body_nested_root = node if not is_shell else None
            if is_shell:
                body_scope = AstichiScope(
                    root=node,
                    label=f"shell {node.name!r} body",
                    parent=scope,
                )
            for decorator in node.decorator_list:
                self._walk(decorator, scope, nested_python_root=nested_python_root)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Preserve pre-refactor asymmetry: shell args/defaults are
                # body-owned, while decorators/returns remain outer-owned.
                self._walk_arguments(
                    node.args,
                    body_scope,
                    nested_python_root=body_nested_root,
                )
                if node.returns is not None:
                    self._walk(
                        node.returns,
                        scope,
                        nested_python_root=nested_python_root,
                    )
            if isinstance(node, ast.ClassDef):
                # Preserve pre-refactor behavior: class bases/keywords are
                # evaluated in the outer scope, not the shell body scope.
                for base in node.bases:
                    self._walk(base, scope, nested_python_root=nested_python_root)
                for keyword in node.keywords:
                    self._walk(keyword, scope, nested_python_root=nested_python_root)
            for child in node.body:
                self._walk(
                    child,
                    body_scope,
                    nested_python_root=body_nested_root,
                )
            return
        for child in ast.iter_child_nodes(node):
            self._walk(child, scope, nested_python_root=nested_python_root)

    def _walk_arguments(
        self,
        args: ast.arguments,
        scope: AstichiScope,
        *,
        nested_python_root: ast.AST | None,
    ) -> None:
        self._record(args, scope, nested_python_root=nested_python_root)
        for argument in (
            list(args.posonlyargs)
            + list(args.args)
            + list(args.kwonlyargs)
        ):
            self._walk(argument, scope, nested_python_root=nested_python_root)
        if args.vararg is not None:
            self._walk(args.vararg, scope, nested_python_root=nested_python_root)
        if args.kwarg is not None:
            self._walk(args.kwarg, scope, nested_python_root=nested_python_root)
        for default in args.defaults + args.kw_defaults:
            if default is not None:
                self._walk(default, scope, nested_python_root=nested_python_root)
