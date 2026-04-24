"""Domain resolution for `astichi_for` loop unrolling.

Given the AST of a domain expression (the sole argument to `astichi_for(...)`),
`resolve_domain` returns the concrete sequence of iteration values or raises
`ValueError` with a descriptive message when the domain is not literal-
resolvable. See `dev-docs/historical/AstichiApiDesignV1-UnrollRevision.md` §7.
"""

from __future__ import annotations

import ast
from typing import Union

from astichi.diagnostics import format_astichi_error

_Scalar = Union[int, float, bool, str, bytes, None]
DomainValue = Union[_Scalar, tuple["DomainValue", ...]]


def resolve_domain(node: ast.expr) -> list[DomainValue]:
    """Resolve an `astichi_for` domain expression to its iteration values.

    Supported shapes:

    - `ast.Tuple` / `ast.List` whose elements are literals or nested
      tuples/lists of literals (tuple structure is preserved so downstream
      unrolling can bind tuple-unpacking loop targets).
    - `ast.Call` of the form `range(N)` / `range(A, B)` / `range(A, B, C)`
      with integer-literal arguments (unary minus on an int literal is
      accepted).

    Every other shape raises `ValueError`.
    """
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_resolve_element(e) for e in node.elts]
    if _is_range_call(node):
        return _resolve_range(node)
    raise ValueError(_reject_domain(node))


_NOT_LITERAL = object()


def _is_range_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
    )


def _resolve_range(node: ast.Call) -> list[int]:
    if node.keywords:
        raise ValueError(
            format_astichi_error(
                "unroll",
                "astichi_for range domain does not accept keyword arguments",
                hint="use `range(stop)` or `range(start, stop)` with positional ints only",
            )
        )
    args = node.args
    if not 1 <= len(args) <= 3:
        raise ValueError(
            format_astichi_error(
                "unroll",
                "astichi_for range domain expects 1 to 3 positional arguments, "
                f"got {len(args)}",
                hint="use `range(N)` or `range(a, b)` or `range(a, b, step)` with integer literals",
            )
        )
    ints: list[int] = []
    for i, arg in enumerate(args):
        value = _literal_int(arg)
        if value is None:
            raise ValueError(
                format_astichi_error(
                    "unroll",
                    f"astichi_for range argument {i} must be an integer literal",
                    hint="only compile-time integer literals (and unary `-`) are allowed in `range(...)`",
                )
            )
        ints.append(value)
    return list(range(*ints))


def _resolve_element(node: ast.expr) -> DomainValue:
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(_resolve_element(e) for e in node.elts)
    value = _literal_value(node)
    if value is _NOT_LITERAL:
        raise ValueError(_reject_domain(node))
    return value  # type: ignore[return-value]


def _literal_value(node: ast.expr) -> object:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, (int, float, bool, str, bytes)) or value is None:
            return value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
        and not isinstance(node.operand.value, bool)
    ):
        return -node.operand.value
    return _NOT_LITERAL


def _literal_int(node: ast.expr) -> int | None:
    value = _literal_value(node)
    if value is _NOT_LITERAL or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _reject_domain(node: ast.expr) -> str:
    kind = type(node).__name__
    if isinstance(node, ast.Name):
        problem = (
            "astichi_for domain must be a literal tuple/list or range(...); "
            f"got bare name {node.id!r} (external-domain support deferred)"
        )
    elif isinstance(node, ast.Call):
        fn = node.func.id if isinstance(node.func, ast.Name) else kind
        problem = (
            "astichi_for domain must be a literal tuple/list or range(...); "
            f"got call to {fn}()"
        )
    elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        problem = f"astichi_for domain must not be a comprehension ({kind})"
    else:
        problem = (
            "astichi_for domain must be a literal tuple/list or range(...); "
            f"got {kind}"
        )
    return format_astichi_error(
        "unroll",
        problem,
        hint=(
            "use a literal tuple/list or `range(...)` for the domain, or bind a "
            "name first with `astichi_bind_external(...)` and `composable.bind(...)`"
        ),
    )
