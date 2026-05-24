"""Shared boundary-prefix helpers for root payload surfaces."""

from __future__ import annotations

import ast

from astichi.lowering.markers import ALL_MARKERS, call_name

BOUNDARY_PREFIX_NAMES = frozenset(
    marker.source_name
    for marker in ALL_MARKERS
    if marker.is_expression_prefix_directive()
)


def is_boundary_prefix_statement(statement: ast.stmt) -> bool:
    """Return true for marker statements allowed before root payloads."""
    if not isinstance(statement, ast.Expr):
        return False
    call = statement.value
    if not isinstance(call, ast.Call):
        return False
    name = call_name(call)
    if name is None:
        return False
    return name in BOUNDARY_PREFIX_NAMES


def first_non_prefix_statement(body: list[ast.stmt]) -> ast.stmt | None:
    """Return the first statement after any boundary-prefix directive block."""
    for statement in body:
        if not is_boundary_prefix_statement(statement):
            return statement
    return None


def single_payload_statement_after_boundary_prefix(
    body: list[ast.stmt],
) -> ast.stmt | None:
    """Return the sole non-prefix statement when root payload shape is unique."""
    payload: ast.stmt | None = None
    for statement in body:
        if is_boundary_prefix_statement(statement):
            continue
        if payload is not None:
            return None
        payload = statement
    return payload


def single_payload_expression_after_boundary_prefix(
    body: list[ast.stmt],
) -> ast.Expr | None:
    """Return the sole non-prefix expression statement, if present."""
    statement = single_payload_statement_after_boundary_prefix(body)
    if isinstance(statement, ast.Expr):
        return statement
    return None


def single_payload_function_after_boundary_prefix(
    body: list[ast.stmt],
    name: str,
    *,
    include_async: bool = True,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Return the sole non-prefix function payload with ``name``, if present."""
    statement = single_payload_statement_after_boundary_prefix(body)
    if isinstance(statement, ast.FunctionDef) or (
        include_async and isinstance(statement, ast.AsyncFunctionDef)
    ):
        if statement.name == name:
            return statement
    return None
