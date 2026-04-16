"""Concrete immutable composable carrier for Astichi V1."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from astichi.lowering import RecognizedMarker
from astichi.model.composable import Composable
from astichi.model.origin import CompileOrigin
from astichi.model.ports import DemandPort, SupplyPort

if TYPE_CHECKING:
    from astichi.hygiene import NameClassification


@dataclass(frozen=True)
class BasicComposable(Composable):
    """First concrete immutable composable implementation."""

    tree: ast.Module
    origin: CompileOrigin
    markers: tuple[RecognizedMarker, ...] = field(default_factory=tuple)
    classification: NameClassification | None = None
    demand_ports: tuple[DemandPort, ...] = field(default_factory=tuple)
    supply_ports: tuple[SupplyPort, ...] = field(default_factory=tuple)

    def emit(self, *, provenance: bool = True) -> str:
        from astichi.emit import emit_source

        return emit_source(self.tree, provenance=provenance)

    def materialize(self) -> "BasicComposable":
        from astichi.materialize import materialize_composable

        return materialize_composable(self)
