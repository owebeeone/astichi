"""Production-path counter guards for the self-native roll-build."""

from __future__ import annotations

from collections import Counter
from typing import Mapping

# Counters that must stay zero on the YIDL lifecycle production success path.
PRODUCTION_FORBIDDEN_COUNTERS: tuple[str, ...] = (
    "rebuild_composable",
    "python_scope_mirror_replay",
    "materialize_composable",
    "assembly_scope_apply",
    "python_compile_ast_parse",
    "python_external_literal_unparse",
    "native_materialize_operation_stream_fallback",
)

# Required once self-native production is active (hybrid baseline may omit some).
PRODUCTION_REQUIRED_COUNTERS: tuple[str, ...] = (
    "copy_python_ast",
    "native_scope_batch_size",
)


def forbidden_production_violations(
    counts: Mapping[str, int],
) -> dict[str, int]:
    """Return forbidden counters with a positive count."""
    return {
        key: int(counts[key])
        for key in PRODUCTION_FORBIDDEN_COUNTERS
        if int(counts.get(key, 0)) > 0
    }


def missing_production_requirements(
    counts: Mapping[str, int],
    *,
    required: tuple[str, ...] = PRODUCTION_REQUIRED_COUNTERS,
) -> tuple[str, ...]:
    """Return required counters that were not observed."""
    return tuple(key for key in required if int(counts.get(key, 0)) <= 0)


def assert_production_forbidden_zero(
    counts: Mapping[str, int],
    *,
    context: str = "production path",
) -> None:
    violations = forbidden_production_violations(counts)
    if not violations:
        return
    detail = ", ".join(f"{key}={value}" for key, value in sorted(violations.items()))
    raise AssertionError(f"{context} forbidden counters: {detail}")


def assert_production_requirements(
    counts: Mapping[str, int],
    *,
    required: tuple[str, ...] = PRODUCTION_REQUIRED_COUNTERS,
    context: str = "production path",
) -> None:
    missing = missing_production_requirements(counts, required=required)
    if not missing:
        return
    raise AssertionError(
        f"{context} missing required counters: {', '.join(missing)}"
    )
