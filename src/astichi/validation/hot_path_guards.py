"""Hot-path guards: no CPython object work until lifecycle handoff.

These are stricter than ``production_guards`` (hybrid fallback removal). The
lifecycle subprocess test is the fool-proof gate for full self-native.
"""

from __future__ import annotations

from typing import Mapping

# Each count is one trip through native parse_module + Emitter (or equivalent).
HOT_PATH_FORBIDDEN_COUNTERS: tuple[str, ...] = (
    "native_compile_parse",
    "native_package_snapshot_extract",
    "python_compile_ast_parse",
    "native_materialize_workspace_copy",
    "rebuild_composable",
    "python_scope_mirror_replay",
    "materialize_composable",
    "assembly_scope_apply",
    "python_external_literal_unparse",
    "native_materialize_operation_stream_fallback",
)

HOT_PATH_HANDOFF_COUNTER = "copy_python_ast"


def hot_path_forbidden_violations(
    counts: Mapping[str, int],
) -> dict[str, int]:
    """Return hot-path forbidden counters with a positive count."""
    return {
        key: int(counts[key])
        for key in HOT_PATH_FORBIDDEN_COUNTERS
        if int(counts.get(key, 0)) > 0
    }


def assert_hot_path_forbidden_zero(
    counts: Mapping[str, int],
    *,
    context: str = "lifecycle hot path",
) -> None:
    violations = hot_path_forbidden_violations(counts)
    if not violations:
        return
    detail = ", ".join(f"{key}={value}" for key, value in sorted(violations.items()))
    raise AssertionError(f"{context} forbidden counters: {detail}")


def assert_hot_path_handoff_shape(
    counts: Mapping[str, int],
    *,
    decorated_classes: int,
    context: str = "lifecycle hot path",
) -> None:
    """Handoff is exactly one CPython artifact build per decorated class."""
    handoff = int(counts.get(HOT_PATH_HANDOFF_COUNTER, 0))
    if handoff == decorated_classes:
        return
    raise AssertionError(
        f"{context} expected {HOT_PATH_HANDOFF_COUNTER}={decorated_classes}, "
        f"got {handoff}"
    )
