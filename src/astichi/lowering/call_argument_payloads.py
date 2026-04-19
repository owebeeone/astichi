"""Recognition and validation for ``astichi_funcargs(...)`` payload snippets."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass


_FUNCARGS_NAME = "astichi_funcargs"
_DIRECTIVE_NAMES: frozenset[str] = frozenset({"astichi_import", "astichi_export"})


@dataclass(frozen=True)
class FuncArgPayloadItem:
    """Base payload item for one authored ``astichi_funcargs(...)`` entry."""


@dataclass(frozen=True)
class PositionalFuncArgItem(FuncArgPayloadItem):
    expr: ast.expr


@dataclass(frozen=True)
class StarredFuncArgItem(FuncArgPayloadItem):
    expr: ast.expr


@dataclass(frozen=True)
class KeywordFuncArgItem(FuncArgPayloadItem):
    name: str
    expr: ast.expr


@dataclass(frozen=True)
class DoubleStarFuncArgItem(FuncArgPayloadItem):
    expr: ast.expr


@dataclass(frozen=True)
class DirectiveFuncArgItem(FuncArgPayloadItem):
    directive_name: str
    name: str
    call: ast.Call


@dataclass(frozen=True)
class FuncArgPayload:
    items: tuple[FuncArgPayloadItem, ...]


def is_astichi_funcargs_call(node: ast.AST) -> bool:
    """Whether ``node`` is an ``astichi_funcargs(...)`` call."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == _FUNCARGS_NAME
    )


def direct_funcargs_directive_calls(call: ast.Call) -> tuple[ast.Call, ...]:
    """Return direct special ``_=astichi_import/export(...)`` carriers in order."""
    directives: list[ast.Call] = []
    for keyword in call.keywords:
        if keyword.arg != "_" or not isinstance(keyword.value, ast.Call):
            continue
        if _call_name(keyword.value) in _DIRECTIVE_NAMES:
            directives.append(keyword.value)
    return tuple(directives)


def extract_funcargs_payload(call: ast.Call) -> FuncArgPayload:
    """Extract one authored ``astichi_funcargs(...)`` call into a payload model."""
    if not is_astichi_funcargs_call(call):
        raise TypeError("extract_funcargs_payload expects an astichi_funcargs(...) call")
    items: list[FuncArgPayloadItem] = []
    for arg in call.args:
        if isinstance(arg, ast.Starred):
            items.append(StarredFuncArgItem(expr=copy.deepcopy(arg.value)))
            continue
        items.append(PositionalFuncArgItem(expr=copy.deepcopy(arg)))
    for keyword in call.keywords:
        if keyword.arg == "_" and _is_direct_directive_call(keyword.value):
            assert isinstance(keyword.value, ast.Call)
            directive_name = _call_name(keyword.value)
            first_arg = keyword.value.args[0]
            assert directive_name is not None
            assert isinstance(first_arg, ast.Name)
            items.append(
                DirectiveFuncArgItem(
                    directive_name=directive_name,
                    name=first_arg.id,
                    call=copy.deepcopy(keyword.value),
                )
            )
            continue
        if keyword.arg is None:
            items.append(DoubleStarFuncArgItem(expr=copy.deepcopy(keyword.value)))
            continue
        items.append(
            KeywordFuncArgItem(
                name=keyword.arg,
                expr=copy.deepcopy(keyword.value),
            )
        )
    return FuncArgPayload(items=tuple(items))


def validate_call_argument_payload_surface(tree: ast.Module) -> None:
    """Reject malformed or misplaced ``astichi_funcargs(...)`` payload snippets."""
    calls = [node for node in ast.walk(tree) if is_astichi_funcargs_call(node)]
    if not calls:
        return
    if (
        len(calls) != 1
        or len(tree.body) != 1
        or not isinstance(tree.body[0], ast.Expr)
        or tree.body[0].value is not calls[0]
    ):
        raise ValueError(
            "astichi_funcargs(...) must appear as the only top-level expression "
            "statement in a call-argument payload snippet"
        )
    _validate_funcargs_call(calls[0])


def _validate_funcargs_call(call: ast.Call) -> None:
    directive_names = {
        directive.args[0].id
        for directive in direct_funcargs_directive_calls(call)
        if directive.args and isinstance(directive.args[0], ast.Name)
    }
    bind_external_names = {
        child.args[0].id
        for child in ast.walk(call)
        if _call_name(child) == "astichi_bind_external"
        and child.args
        and isinstance(child.args[0], ast.Name)
    }
    for name in sorted(directive_names & bind_external_names):
        raise ValueError(
            "payload-local astichi_import/export and astichi_bind_external may "
            f"not share the same name `{name}` inside astichi_funcargs(...)"
        )
    for arg in call.args:
        if _contains_non_value_directive(arg):
            raise ValueError(
                "astichi_import(...) / astichi_export(...) are only valid as "
                "direct _= carriers inside astichi_funcargs(...)"
            )
    for keyword in call.keywords:
        value = keyword.value
        if keyword.arg == "_":
            if _is_direct_directive_call(value):
                continue
            if _call_name(value) == "astichi_pass":
                raise ValueError(
                    "astichi_pass(...) is not valid in _= inside "
                    "astichi_funcargs(...); use it in a real argument "
                    "expression instead"
                )
            if _contains_non_value_directive(value):
                raise ValueError(
                    "astichi_import(...) / astichi_export(...) must be direct "
                    "_= carriers inside astichi_funcargs(...); wrapped forms "
                    "are not supported"
                )
            continue
        if _contains_non_value_directive(value):
            raise ValueError(
                "astichi_import(...) / astichi_export(...) are only valid as "
                "direct _= carriers inside astichi_funcargs(...)"
            )


def _contains_non_value_directive(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _call_name(child) in _DIRECTIVE_NAMES:
            return True
    return False


def _is_direct_directive_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) in _DIRECTIVE_NAMES


def _call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Name):
        return None
    return node.func.id
