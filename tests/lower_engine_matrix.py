"""Shared helpers for dual lower-engine pytest matrix runs."""

from __future__ import annotations

import os

from astichi.lower_engine.native import load_native_extension, select_lower_engine

ENGINE_SELECTION_ENV = "ASTICHI_LOWER_ENGINE"
MATRIX_ENV = "ASTICHI_LOWER_ENGINE_MATRIX"
DEFAULT_MATRIX_ENGINES = ("python", "native")

_EXEMPT_MODULE_PREFIXES = (
    "test_native_engine_",
    "test_native_success_path_guards",
    "test_native_self_native_f0c",
    "test_native_literal_payload_abi",
    "test_native_compile_validation_f3b",
    "test_native_compile_oracle_f3c",
    "test_native_compile_no_python_parse_f3d",
    "test_native_materialize_oracle_f4c",
    "test_native_materialize_no_python_fallback_f4d",
    "test_native_handoff_f4e",
    "test_native_handoff_transfer_f6",
    "test_lifecycle_hot_path_python_gate",
    "test_hot_path_h4_production_green",
    "test_native_hot_path_no_pydict_h2",
    "test_o3_production_compile",
    "test_validation_perf_helper",
    "test_versioned_test_harness",
)


def matrix_enabled() -> bool:
    """Return whether pytest should run the dual lower-engine matrix."""
    value = os.environ.get(MATRIX_ENV, "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def matrix_exempt_module(module_name: str) -> bool:
    """Return whether a test module opts out of dual-engine collection."""
    short_name = module_name.rsplit(".", 1)[-1]
    return short_name.startswith(_EXEMPT_MODULE_PREFIXES)


def available_matrix_engines() -> tuple[str, ...]:
    """Return lower-engine request values to run in the matrix."""
    engines: list[str] = ["python"]
    if load_native_extension(required=False) is not None:
        if select_lower_engine("native").selected_engine != "python":
            engines.append("native")
    return tuple(engines)


def matrix_variant_suffix(engine: str) -> str:
    """Return the pytest node suffix for one matrix engine request."""
    return f"[lower_engine={engine}]"


def node_uses_matrix_variant(nodeid: str) -> bool:
    """Return whether a collected node id names one matrix engine variant."""
    return "[lower_engine=" in nodeid
