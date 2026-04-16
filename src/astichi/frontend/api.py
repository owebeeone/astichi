"""Public frontend entrypoints for Astichi."""

from __future__ import annotations

from astichi.model import Composable


def compile(
    source: str,
    file_name: str | None = None,
    line_number: int = 1,
    offset: int = 0,
) -> Composable:
    """Compile marker-bearing source into a composable."""
    raise NotImplementedError("astichi.compile is not implemented yet")
