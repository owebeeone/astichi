"""Behavior-bearing marker recognition contexts."""

from __future__ import annotations

from dataclasses import dataclass

from astichi.model.semantics import SemanticSingleton


class MarkerContext(SemanticSingleton):
    """Where a marker was recognized."""

    def is_call_context(self) -> bool:
        return False

    def is_decorator_context(self) -> bool:
        return False

    def is_identifier_context(self) -> bool:
        return False

    def is_definitional_context(self) -> bool:
        return False


@dataclass(frozen=True, eq=False)
class _CallContext(MarkerContext):
    name: str = "call"

    def is_call_context(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _DecoratorContext(MarkerContext):
    name: str = "decorator"

    def is_decorator_context(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _IdentifierContext(MarkerContext):
    name: str = "identifier"

    def is_identifier_context(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _DefinitionalContext(MarkerContext):
    name: str = "definitional"

    def is_definitional_context(self) -> bool:
        return True


CALL_CONTEXT = _CallContext()
DECORATOR_CONTEXT = _DecoratorContext()
IDENTIFIER_CONTEXT = _IdentifierContext()
DEFINITIONAL_CONTEXT = _DefinitionalContext()
