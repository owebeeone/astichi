"""Predicates for internal ``astichi_insert`` surfaces."""

from __future__ import annotations

from collections.abc import Iterable
import ast


def is_astichi_insert_call(node: ast.AST) -> bool:
    """Whether ``node`` is a direct ``astichi_insert(...)`` call."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "astichi_insert"
    )


def is_expression_insert_call(node: ast.AST) -> bool:
    """Whether ``node`` is expression-form ``astichi_insert(target, payload)``."""
    return is_astichi_insert_call(node) and len(node.args) == 2


def has_astichi_insert_decorator(decorators: Iterable[ast.expr]) -> bool:
    """Whether a decorator list contains direct ``@astichi_insert(...)``."""
    return any(is_astichi_insert_call(decorator) for decorator in decorators)


def is_astichi_insert_shell(node: ast.AST) -> bool:
    """Whether ``node`` is a class/def decorated by ``astichi_insert(...)``."""
    return (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and has_astichi_insert_decorator(node.decorator_list)
    )
