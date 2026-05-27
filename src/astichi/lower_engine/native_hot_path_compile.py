"""Hot-path compile: Rust package registration without CPython AST parse."""

from __future__ import annotations

import ast
import os

from astichi.lower_engine.native import native_capabilities, select_effective_lower_engine
from astichi.lower_engine.self_native import has_self_native_production
from astichi.lower_engine.self_native import SELF_NATIVE_NO_PYTHON_PARSE_COMPILE_FEATURE

_HOT_PATH_PLACEHOLDER_ATTR = "_astichi_hot_path_placeholder"

_MATRIX_ENV = "ASTICHI_LOWER_ENGINE_MATRIX"


def native_hot_path_compile_enabled() -> bool:
    capabilities = native_capabilities()
    if capabilities is None:
        return False
    features = capabilities.get("engine_features", ())
    return SELF_NATIVE_NO_PYTHON_PARSE_COMPILE_FEATURE in features


def lower_engine_matrix_active() -> bool:
    """True while pytest is driving the dual python/native matrix."""
    value = os.environ.get(_MATRIX_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def o3_production_hot_path_compile_active() -> bool:
    """True when compile should use placeholder + Rust package only (no parse).

    Active for lifecycle gate subprocesses (``collect_perf_counters``) and for
    real production import (self-native engine, matrix disabled).
    """
    if not native_hot_path_compile_enabled():
        return False
    from astichi.perf_counters import active_perf_counters

    if active_perf_counters() is not None:
        return True
    if lower_engine_matrix_active():
        return False
    capabilities = native_capabilities()
    if capabilities is None or not has_self_native_production(capabilities):
        return False
    return select_effective_lower_engine().selected_engine in {
        "native-rust",
        "native-cpp",
    }


def hot_path_compile_placeholder_tree() -> ast.Module:
    """Return a private placeholder tree used before materialize handoff."""
    tree = ast.Module(body=[ast.Pass()], type_ignores=[])
    setattr(tree, _HOT_PATH_PLACEHOLDER_ATTR, True)
    return tree


def is_hot_path_placeholder_tree(tree: ast.Module) -> bool:
    """True when ``tree`` is an explicit hot-path compile placeholder."""
    return bool(getattr(tree, _HOT_PATH_PLACEHOLDER_ATTR, False))


def resolve_hot_path_materialization_tree(
    *,
    tree: ast.Module,
    native_source: str | None,
    file_name: str,
) -> ast.Module | None:
    """Return a parsed tree when compile registered a placeholder module body.

    Lifecycle production materializes through ``AssemblyScope.build`` native
    handoff; this helper is for ``build_merge`` / ``materialize_composable`` on
    composables that never went through scope assembly.
    """
    if not is_hot_path_placeholder_tree(tree):
        return None
    if native_source is None:
        return None
    from astichi.lower_engine.native_compile_parse import (
        native_compile_tree_from_parse_source,
    )

    return native_compile_tree_from_parse_source(
        native_source,
        file_name=file_name,
    )
