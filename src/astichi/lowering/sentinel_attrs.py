"""Helpers for transparent sentinel attributes on marker calls.

The first immediate ``.astichi_v`` / ``._`` segment after certain
marker calls is compile-time-only surface sugar. Lowering strips that
single segment and reuses the attribute node's expression context on
the lowered replacement.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable


TRANSPARENT_SENTINEL_ATTRS: frozenset[str] = frozenset({"astichi_v", "_"})


@dataclass(frozen=True)
class TransparentSentinelMatch:
    """Matched one-shot transparent sentinel wrapper."""

    call: ast.Call
    ctx: ast.expr_context


def match_transparent_sentinel(
    node: ast.AST,
    *,
    is_marker_call: Callable[[ast.Call], bool],
) -> TransparentSentinelMatch | None:
    """Return the wrapped call when ``node`` is ``Call(...).<sentinel>``."""
    if not isinstance(node, ast.Attribute):
        return None
    if node.attr not in TRANSPARENT_SENTINEL_ATTRS:
        return None
    if not isinstance(node.value, ast.Call):
        return None
    if not is_marker_call(node.value):
        return None
    return TransparentSentinelMatch(call=node.value, ctx=node.ctx)
