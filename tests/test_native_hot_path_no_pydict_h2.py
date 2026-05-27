"""H2: hot-path compile avoids canonical package-v2 PyDict snapshot extraction."""

from __future__ import annotations

import pytest

import astichi
from astichi.lower_engine.native import load_native_extension, reset_native_extension_cache
from astichi.lower_engine.native_hot_path_compile import native_hot_path_compile_enabled
from astichi.lower_engine.self_native import SELF_NATIVE_NO_PYDICT_SNAPSHOTS_FEATURE
from astichi.lower_engine.self_native_gates import native_no_pydict_snapshots_enabled
from astichi.perf_counters import collect_perf_counters
from astichi.validation.hot_path_guards import assert_hot_path_forbidden_zero


def test_no_pydict_snapshots_capability_when_built() -> None:
    from astichi.lower_engine.native import native_capabilities

    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")
    if SELF_NATIVE_NO_PYDICT_SNAPSHOTS_FEATURE not in capabilities.get(
        "engine_features", ()
    ):
        pytest.skip("rebuild native_engine for H2 no_pydict_snapshots capability")
    assert native_no_pydict_snapshots_enabled() is True


def test_hot_path_compile_skips_package_snapshot_extract_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_hot_path_compile_enabled():
        pytest.skip("hot-path compile capability not advertised")
    if not native_no_pydict_snapshots_enabled():
        pytest.skip("H2 no_pydict_snapshots capability not advertised")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    reset_native_extension_cache()
    with collect_perf_counters() as counters:
        binding = astichi.compile("result = astichi_hole(value)\n")._lower_template

    counts = counters.snapshot()["counts"]
    assert counts.get("native_package_snapshot_extract", 0) == 0
    assert counts.get("native_compile_parse", 0) == 0
    assert binding is not None
    assert binding.native_package_snapshot is None
    assert binding.native_compile_template_handle is not None
    assert binding.package_v2.records


def test_lifecycle_gate_forbids_package_snapshot_extract() -> None:
    from tests.test_lifecycle_hot_path_python_gate import (
        _run_lifecycle_baseline_subprocess,
    )

    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")
    if not native_no_pydict_snapshots_enabled():
        pytest.skip("H2 no_pydict_snapshots capability not advertised")

    summary = _run_lifecycle_baseline_subprocess()
    counts = summary["astichi_counters"]["counts"]
    assert_hot_path_forbidden_zero(counts)
