"""Producer-list interface implemented by assembler clients."""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from astichi.assembler.client.actionapi import AssemblyAction
from astichi.assembler.client.nodeapi import AssemblyContext, ProducerNode


class ProducerList(ABC):
    """Client producer list that expands visible data into assembly actions."""

    @abstractmethod
    def producer_nodes(self, context: AssemblyContext) -> Iterable[ProducerNode]:
        """Return producer nodes visible in this scope context."""

    @abstractmethod
    def actions_for(
        self, node: ProducerNode, context: AssemblyContext
    ) -> Iterable[AssemblyAction]:
        """Return zero or more actions selected for one producer node."""
