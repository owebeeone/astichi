"""Shape semantics for Astichi marker usage."""

from __future__ import annotations

from abc import ABC


class MarkerShape(ABC):
    """Behavior-bearing marker usage shape."""

    def is_scalar_expr(self) -> bool:
        return False

    def is_positional_variadic(self) -> bool:
        return False

    def is_named_variadic(self) -> bool:
        return False

    def is_block(self) -> bool:
        return False


class _ScalarExprShape(MarkerShape):
    def is_scalar_expr(self) -> bool:
        return True


class _PositionalVariadicShape(MarkerShape):
    def is_positional_variadic(self) -> bool:
        return True


class _NamedVariadicShape(MarkerShape):
    def is_named_variadic(self) -> bool:
        return True


class _BlockShape(MarkerShape):
    def is_block(self) -> bool:
        return True


SCALAR_EXPR = _ScalarExprShape()
POSITIONAL_VARIADIC = _PositionalVariadicShape()
NAMED_VARIADIC = _NamedVariadicShape()
BLOCK = _BlockShape()
