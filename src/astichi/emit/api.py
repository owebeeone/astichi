"""Source emission for Astichi V1."""

from __future__ import annotations

import ast


def emit_source(tree: ast.Module) -> str:
    """Emit valid Python source text from an AST module."""
    text = ast.unparse(tree)
    if not text.endswith("\n"):
        text += "\n"
    return text
