"""O3 production compile: no Python parse on real import (matrix disabled)."""

from __future__ import annotations

import ast
import os

import pytest

import astichi
from astichi.lower_engine.native_hot_path_compile import (
    is_hot_path_placeholder_tree,
    native_hot_path_compile_enabled,
    o3_production_hot_path_compile_active,
)
from astichi.lower_engine.native import load_native_extension
from astichi.perf_counters import collect_perf_counters


def test_o3_production_compile_active_without_perf_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_hot_path_compile_enabled():
        pytest.skip("F3d no_python_parse capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    monkeypatch.delenv("ASTICHI_LOWER_ENGINE_MATRIX", raising=False)

    assert o3_production_hot_path_compile_active() is True


def test_matrix_env_disables_o3_production_compile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_hot_path_compile_enabled():
        pytest.skip("F3d no_python_parse capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE_MATRIX", "1")

    assert o3_production_hot_path_compile_active() is False


def test_production_compile_uses_placeholder_without_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_hot_path_compile_enabled():
        pytest.skip("F3d no_python_parse capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    monkeypatch.delenv("ASTICHI_LOWER_ENGINE_MATRIX", raising=False)

    compiled = astichi.compile("result = astichi_hole(value)\n")
    assert is_hot_path_placeholder_tree(compiled.tree)
    assert compiled.markers == ()


def test_production_compile_skips_python_ast_parse_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_hot_path_compile_enabled():
        pytest.skip("F3d no_python_parse capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    monkeypatch.delenv("ASTICHI_LOWER_ENGINE_MATRIX", raising=False)

    with collect_perf_counters() as counters:
        astichi.compile("result = astichi_hole(value)\n")

    snapshot = counters.snapshot()["counts"]
    assert snapshot.get("python_compile_ast_parse", 0) == 0
    assert snapshot.get("native_compile_parse", 0) == 0


def test_lifecycle_style_import_compile_batch_uses_o3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_hot_path_compile_enabled():
        pytest.skip("F3d no_python_parse capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    monkeypatch.delenv("ASTICHI_LOWER_ENGINE_MATRIX", raising=False)

    snippets = (
        "astichi_hole(body)\n",
        "def astichi_params(*, value__astichi_arg__):\n    pass\n",
        "value = astichi_ref(external=path)\n",
    )
    for source in snippets:
        compiled = astichi.compile(source)
        assert isinstance(compiled.tree, ast.Module)
        assert is_hot_path_placeholder_tree(compiled.tree)
