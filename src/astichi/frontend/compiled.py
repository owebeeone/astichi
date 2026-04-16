"""Frontend-owned compiled composable artifacts."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from astichi.model import Composable


@dataclass(frozen=True)
class CompileOrigin:
    """Source-origin metadata for a compiled snippet."""

    file_name: str
    line_number: int
    offset: int


@dataclass(frozen=True)
class FrontendComposable(Composable):
    """Provisional composable produced by the frontend pipeline."""

    tree: ast.Module
    origin: CompileOrigin
    markers: tuple[object, ...] = field(default_factory=tuple)

    def emit(self, *, provenance: bool = True) -> str:
        raise NotImplementedError("FrontendComposable.emit is not implemented yet")

    def materialize(self) -> object:
        raise NotImplementedError(
            "FrontendComposable.materialize is not implemented yet"
        )
