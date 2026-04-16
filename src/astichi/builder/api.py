"""Public builder entrypoints for Astichi."""

from __future__ import annotations

from astichi.builder.handles import BuilderHandle


def build() -> BuilderHandle:
    """Create a new Astichi builder."""
    return BuilderHandle()
