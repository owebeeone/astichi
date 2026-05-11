"""Client action objects returned during assembler expansion."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import TypeAlias

from astichi.assembler.client.nodeapi import ScopeNode
from astichi.assembler.scope import BindingResource, DemandSelector

BuildIndex: TypeAlias = int | tuple[int, ...]


class AssemblyAction(ABC):
    """One client-selected assembly action for the current scope."""


@dataclass(frozen=True)
class ApplyResource(AssemblyAction):
    """Apply one resource to a matching demand in the current scope."""

    resource: BindingResource
    selector: DemandSelector


@dataclass(frozen=True)
class BuildChildScope(AssemblyAction):
    """Build a child scope and apply its result to the current scope."""

    node: ScopeNode
    selector: DemandSelector
    build_name: str
    build_index: BuildIndex | None = None
    order: int = 0


def demand_selector(
    *,
    name: str | None = None,
    build_match: tuple[str, ...] | None = None,
    owner_match: tuple[str, ...] | None = None,
) -> DemandSelector:
    """Create a demand selector for holes, external binds, or identifiers."""
    return DemandSelector(
        name=name,
        build_match=build_match,
        owner_match=owner_match,
    )


def apply_resource(
    resource: BindingResource,
    *,
    name: str | None = None,
    build_match: tuple[str, ...] | None = None,
    owner_match: tuple[str, ...] | None = None,
) -> ApplyResource:
    """Create an action that applies a resource in the current scope."""
    return ApplyResource(
        resource=resource,
        selector=demand_selector(
            name=name,
            build_match=build_match,
            owner_match=owner_match,
        ),
    )


def build_child_scope(
    node: ScopeNode,
    *,
    build_name: str,
    name: str | None = None,
    build_match: tuple[str, ...] | None = None,
    owner_match: tuple[str, ...] | None = None,
    build_index: BuildIndex | None = None,
    order: int = 0,
) -> BuildChildScope:
    """Create an action that builds a child scope then applies its result."""
    return BuildChildScope(
        node=node,
        selector=demand_selector(
            name=name,
            build_match=build_match,
            owner_match=owner_match,
        ),
        build_name=build_name,
        build_index=build_index,
        order=order,
    )
