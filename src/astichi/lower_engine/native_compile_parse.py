"""Native compile-time parse entrypoints (F3d)."""

from __future__ import annotations

import ast

from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.lower_engine.self_native import SELF_NATIVE_NO_PYTHON_PARSE_COMPILE_FEATURE
from astichi.perf_counters import active_perf_counters


def native_no_python_parse_compile_enabled() -> bool:
    capabilities = native_capabilities()
    if capabilities is None:
        return False
    features = capabilities.get("engine_features", ())
    return SELF_NATIVE_NO_PYTHON_PARSE_COMPILE_FEATURE in features


def native_compile_tree_from_parse_source(
    parse_source: str,
    *,
    file_name: str,
) -> ast.Module:
    """Parse compile input with the native parser and return a CPython ``ast.Module``."""
    module = load_native_extension(required=True)
    assert module is not None
    counters = active_perf_counters()
    if counters is None:
        tree = module.parse_module(parse_source, file_name, "native")
    else:
        with counters.measure("native_compile_parse"):
            tree = module.parse_module(parse_source, file_name, "native")
    if not isinstance(tree, ast.Module):
        raise TypeError("native parse_module must return ast.Module")
    return tree
