"""Recognition helpers for function-parameter payload snippets."""

from __future__ import annotations

import ast
import copy

from astichi.lowering.markers import RecognizedMarker, strip_identifier_suffix

PARAMS_PAYLOAD_NAME = "astichi_params"


def is_astichi_params_def(node: ast.AST) -> bool:
    return (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == PARAMS_PAYLOAD_NAME
    )


def validate_parameter_payload_surface(tree: ast.Module) -> None:
    """Reject malformed ``def astichi_params(...): ...`` payload snippets."""
    payloads = [node for node in ast.walk(tree) if is_astichi_params_def(node)]
    if not payloads:
        return
    if (
        len(payloads) != 1
        or len(tree.body) != 1
        or tree.body[0] is not payloads[0]
    ):
        raise ValueError(
            "def astichi_params(...): pass must be the only top-level statement "
            "in a parameter payload snippet"
        )
    payload = payloads[0]
    if payload.args.posonlyargs:
        raise ValueError("astichi_params payloads do not support positional-only parameters")
    if not _body_is_empty_equivalent(payload.body):
        raise ValueError(
            "astichi_params payload body must be empty-equivalent: pass or ..."
        )


def validate_parameter_hole_surface(
    tree: ast.Module, markers: tuple[RecognizedMarker, ...]
) -> None:
    """Reject malformed ``__astichi_param_hole__`` target markers."""
    valid_arg_ids: set[int] = set()
    defaulted_arg_ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for argument in node.args.args:
            valid_arg_ids.add(id(argument))
        positional = list(node.args.posonlyargs) + list(node.args.args)
        if node.args.defaults:
            for argument in positional[-len(node.args.defaults):]:
                defaulted_arg_ids.add(id(argument))
        for argument in _all_arguments(node.args):
            if argument.arg == "__astichi_param_hole__":
                raise ValueError(
                    "astichi_param_hole_identifier requires an identifier prefix "
                    "before __astichi_param_hole__"
                )

    seen_by_function: dict[int, set[str]] = {}
    function_for_arg = _function_for_arg(tree)
    for marker in markers:
        if marker.source_name != "astichi_param_hole_identifier":
            continue
        if not isinstance(marker.node, ast.arg) or id(marker.node) not in valid_arg_ids:
            raise ValueError(
                "parameter-hole marker __astichi_param_hole__ may appear only as "
                "an ordinary positional-or-keyword function parameter"
            )
        if marker.node.annotation is not None or id(marker.node) in defaulted_arg_ids:
            raise ValueError(
                "parameter-hole marker parameters may not have annotations or defaults"
            )
        assert marker.name_id is not None
        owner_id = function_for_arg[id(marker.node)]
        owner_seen = seen_by_function.setdefault(owner_id, set())
        if marker.name_id in owner_seen:
            raise ValueError(
                f"duplicate parameter-hole target `{marker.name_id}` in one function signature"
            )
        owner_seen.add(marker.name_id)


def extract_params_payload_from_body(body: list[ast.stmt]) -> ast.arguments | None:
    if len(body) != 1 or not is_astichi_params_def(body[0]):
        return None
    payload = body[0]
    assert isinstance(payload, (ast.FunctionDef, ast.AsyncFunctionDef))
    return copy.deepcopy(payload.args)


def has_params_payload(body: list[ast.stmt]) -> bool:
    return extract_params_payload_from_body(body) is not None


def _body_is_empty_equivalent(body: list[ast.stmt]) -> bool:
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return True
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    )


def _all_arguments(args: ast.arguments) -> tuple[ast.arg, ...]:
    result = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    if args.vararg is not None:
        result.append(args.vararg)
    if args.kwarg is not None:
        result.append(args.kwarg)
    return tuple(result)


def _function_for_arg(tree: ast.Module) -> dict[int, int]:
    result: dict[int, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for argument in _all_arguments(node.args):
            result[id(argument)] = id(node)
    return result


def param_hole_name(argument: ast.arg) -> str | None:
    base, marker = strip_identifier_suffix(argument.arg)
    if marker is None or marker.source_name != "astichi_param_hole_identifier":
        return None
    return base
