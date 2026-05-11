"""Scope recipe and top-level client interfaces for assembler expansion."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass

from astichi.assembler.client.nodeapi import AssemblyContext, ScopeNode
from astichi.assembler.client.producerapi import ProducerList
from astichi.assembler.scope import ComposableResource


@dataclass(frozen=True)
class ScopeRecipe:
    """Client recipe for creating and expanding one Astichi scope."""

    root: ComposableResource
    producer_lists: tuple[ProducerList, ...] = ()


class AssemblerClient(ABC):
    """Client contract used by an assembler driver to expand scope trees."""

    @abstractmethod
    def root_nodes(self) -> Iterable[ScopeNode]:
        """Return requested root artifact scope nodes."""

    @abstractmethod
    def context_for_root(self, node: ScopeNode) -> AssemblyContext:
        """Return the root context for a requested scope node."""

    @abstractmethod
    def context_for_child(
        self, parent_context: AssemblyContext, node: ScopeNode
    ) -> AssemblyContext:
        """Return a child context for a child-scope action."""

    @abstractmethod
    def recipe_for(
        self, node: ScopeNode, context: AssemblyContext
    ) -> ScopeRecipe:
        """Return the scope recipe for one client scope node."""


def scope_recipe(
    root: ComposableResource,
    *,
    producer_lists: Iterable[ProducerList] = (),
) -> ScopeRecipe:
    """Create a scope recipe from a named root resource and producer lists."""
    return ScopeRecipe(root=root, producer_lists=tuple(producer_lists))
