"""Public frontend entrypoints for Astichi."""

from __future__ import annotations

import ast

from astichi.frontend.compiled import CompileOrigin, FrontendComposable
from astichi.lowering import recognize_markers
from astichi.model import Composable


def _single_line_source(source: str) -> bool:
    """Return whether source is logically one line."""
    return "\n" not in source.rstrip("\n")


def _padded_source(
    source: str,
    *,
    line_number: int,
    offset: int,
    apply_offset: bool,
) -> str:
    """Construct parse input with source-origin padding applied."""
    prefix = "\n" * max(line_number - 1, 0)
    if apply_offset and offset > 0:
        prefix += " " * offset
    return prefix + source


def compile(
    source: str,
    file_name: str | None = None,
    line_number: int = 1,
    offset: int = 0,
) -> Composable:
    """Compile marker-bearing source into a composable."""
    origin = CompileOrigin(
        file_name=file_name or "<astichi>",
        line_number=line_number,
        offset=offset,
    )
    apply_offset = _single_line_source(source)
    try:
        tree = ast.parse(
            _padded_source(
                source,
                line_number=line_number,
                offset=offset,
                apply_offset=apply_offset,
            ),
            filename=origin.file_name,
        )
    except IndentationError:
        if not apply_offset or offset <= 0:
            raise
        tree = ast.parse(
            _padded_source(
                source,
                line_number=line_number,
                offset=offset,
                apply_offset=False,
            ),
            filename=origin.file_name,
        )
    return FrontendComposable(tree=tree, origin=origin, markers=recognize_markers(tree))
