"""F3d / hot path: compile registers native package without CPython AST parse."""

from __future__ import annotations

import ast

import pytest

import astichi
from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.lower_engine.native_hot_path_compile import native_hot_path_compile_enabled
from astichi.lower_engine.self_native import (
    SELF_NATIVE_NO_PYTHON_PARSE_COMPILE_FEATURE,
)
from astichi.perf_counters import collect_perf_counters


def test_no_python_parse_capability_when_built() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")
    if SELF_NATIVE_NO_PYTHON_PARSE_COMPILE_FEATURE not in capabilities.get(
        "engine_features", ()
    ):
        pytest.skip("rebuild native_engine for F3d no_python_parse capability")
    assert native_hot_path_compile_enabled() is True


def test_native_compile_skips_python_ast_parse_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_hot_path_compile_enabled():
        pytest.skip("F3d no_python_parse capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    with collect_perf_counters() as counters:
        compiled = astichi.compile("result = astichi_hole(value)\n")

    counts = counters.snapshot()["counts"]
    assert counts.get("python_compile_ast_parse", 0) == 0
    assert counts.get("native_compile_parse", 0) == 0
    assert compiled.inventory.records


def test_native_hot_path_compile_uses_placeholder_until_materialize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_hot_path_compile_enabled():
        pytest.skip("F3d no_python_parse capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    with collect_perf_counters():
        compiled = astichi.compile("result = astichi_hole(value)\n")
    assert isinstance(compiled.tree, ast.Module)
    assert len(compiled.tree.body) == 1
    assert isinstance(compiled.tree.body[0], ast.Pass)
