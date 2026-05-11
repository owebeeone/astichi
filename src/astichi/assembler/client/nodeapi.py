"""Client-owned node and context interfaces for assembler expansion."""

from __future__ import annotations

from abc import ABC, abstractmethod

from astichi.assembler.scope import BindingResource


class ScopeNode(ABC):
    """Client data node that opens one Astichi assembly scope."""

    @abstractmethod
    def scope_label(self) -> str:
        """Return a stable label for this scope node."""


class ProducerNode(ABC):
    """Client data node consumed by a producer list inside one scope."""

    @abstractmethod
    def producer_label(self) -> str:
        """Return a stable label for this producer node."""


class AssemblyContext(ABC):
    """Client data view for one scope, including access to parent context."""

    @abstractmethod
    def scope_node(self) -> ScopeNode:
        """Return the client node that created this scope context."""

    @abstractmethod
    def parent_context(self) -> AssemblyContext | None:
        """Return the parent scope context when this is a child scope."""

    @abstractmethod
    def lookup_resource(self, name: str) -> BindingResource | None:
        """Return a named resource visible from this context, if present."""
