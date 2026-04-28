"""Composable interface for Astichi."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astichi.model.descriptors import ComposableDescription


class Composable(ABC):
    """Abstract semantic carrier for Astichi composition."""

    @abstractmethod
    def emit(self, *, provenance: bool = True) -> str:
        """Emit source text for this composable."""

    @abstractmethod
    def materialize(self) -> object:
        """Materialize this composable into a runnable/emittable artifact."""

    @abstractmethod
    def describe(self) -> "ComposableDescription":
        """Return immutable public composition metadata for this composable."""
