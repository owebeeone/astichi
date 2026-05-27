"""Self-native production contract: caps + lifecycle counter shape (H4)."""

from __future__ import annotations

from typing import Mapping

from astichi.validation.hot_path_guards import (
    assert_hot_path_forbidden_zero,
    assert_hot_path_handoff_shape,
)
from astichi.validation.production_guards import (
    assert_production_forbidden_zero,
    assert_production_requirements,
)


def assert_self_native_production_green(
    counts: Mapping[str, int],
    *,
    decorated_classes: int,
    context: str = "self-native production",
) -> None:
    """Assert advertised ``current_surfaces`` matches a real hot-path lifecycle."""
    assert_hot_path_forbidden_zero(counts, context=context)
    assert_hot_path_handoff_shape(
        counts,
        decorated_classes=decorated_classes,
        context=context,
    )
    assert_production_forbidden_zero(counts, context=context)
    assert_production_requirements(counts, context=context)
