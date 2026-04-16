"""Public builder entrypoints for Astichi."""

from __future__ import annotations

from astichi.builder.graph import BuilderGraph


def build() -> BuilderGraph:
    """Create a new Astichi builder."""
    return BuilderGraph()
