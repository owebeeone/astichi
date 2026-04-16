"""Composable interface for Astichi."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Composable(ABC):
    """Abstract semantic carrier for Astichi composition."""

    @abstractmethod
    def emit(self, *, provenance: bool = True) -> str:
        """Emit source text for this composable."""

    @abstractmethod
    def materialize(self) -> object:
        """Materialize this composable into a runnable/emittable artifact."""
