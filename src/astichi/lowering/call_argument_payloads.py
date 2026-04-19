"""Recognition and validation for ``astichi_funcargs(...)`` payload snippets."""

from __future__ import annotations

import ast


_FUNCARGS_NAME = "astichi_funcargs"
_DIRECTIVE_NAMES: frozenset[str] = frozenset({"astichi_import", "astichi_export"})


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
