"""Source-origin metadata for Astichi composables."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompileOrigin:
    """Source-origin metadata for a compiled snippet."""

    file_name: str
    line_number: int
    offset: int
