"""Behavior-bearing source-kind values for frontend compilation."""

from __future__ import annotations

from dataclasses import dataclass

from astichi.model.semantics import SemanticSingleton


class SourceKind(SemanticSingleton):
    """Kind of source accepted by the frontend."""

    def allows_internal_insert_metadata(self) -> bool:
        return False

    def validates_authored_payload_surfaces(self) -> bool:
        return True


@dataclass(frozen=True, eq=False)
class _AuthoredSource(SourceKind):
    name: str = "authored"


@dataclass(frozen=True, eq=False)
class _AstichiEmittedSource(SourceKind):
    name: str = "astichi-emitted"

    def allows_internal_insert_metadata(self) -> bool:
        return True

    def validates_authored_payload_surfaces(self) -> bool:
        return False


AUTHORED_SOURCE = _AuthoredSource()
ASTICHI_EMITTED_SOURCE = _AstichiEmittedSource()


def normalize_source_kind(value: SourceKind | str) -> SourceKind:
    """Normalize public/source-boundary source-kind spelling."""
    if isinstance(value, SourceKind):
        return value
    if value == AUTHORED_SOURCE.name:
        return AUTHORED_SOURCE
    if value == ASTICHI_EMITTED_SOURCE.name:
        return ASTICHI_EMITTED_SOURCE
    raise ValueError(
        "source_kind must be 'authored' or 'astichi-emitted'; "
        f"got {value!r}"
    )
