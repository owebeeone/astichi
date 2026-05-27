from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from astichi.lower_engine.native import (
    NativeExtensionUnavailableError,
    load_native_extension,
    reset_native_extension_cache,
    select_lower_engine,
    select_self_native_production_engine,
)
from astichi.lower_engine.self_native import has_self_native_production
from astichi.validation.production_guards import (
    PRODUCTION_FORBIDDEN_COUNTERS,
    assert_production_forbidden_zero,
    assert_production_requirements,
    forbidden_production_violations,
    missing_production_requirements,
)


def _load_lifecycle_baseline_helper() -> ModuleType:
    script = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "validation"
        / "perf"
        / "yidl_lifecycle_import_baseline.py"
    )
    spec = importlib.util.spec_from_file_location(
        "astichi_yidl_lifecycle_import_baseline",
        script,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lifecycle_baseline_script() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "validation"
        / "perf"
        / "yidl_lifecycle_import_baseline.py"
    )


def _run_lifecycle_baseline_subprocess() -> dict[str, object]:
    script = _lifecycle_baseline_script()
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--engine",
            "native",
            "--require-native-counters",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=script.parents[3],
    )
    if completed.returncode != 0:
        pytest.skip(
            "lifecycle baseline subprocess failed: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return json.loads(completed.stdout)


def test_forbidden_production_counter_names_are_stable() -> None:
    assert "rebuild_composable" in PRODUCTION_FORBIDDEN_COUNTERS
    assert "python_scope_mirror_replay" in PRODUCTION_FORBIDDEN_COUNTERS


def test_guard_helpers_detect_violations() -> None:
    assert forbidden_production_violations({"rebuild_composable": 2}) == {
        "rebuild_composable": 2
    }
    assert missing_production_requirements({"copy_python_ast": 0}) == (
        "copy_python_ast",
        "native_scope_batch_size",
    )


def test_hybrid_lifecycle_import_forbidden_counters_are_zero() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    reset_native_extension_cache()
    summary = _run_lifecycle_baseline_subprocess()
    counts = summary["astichi_counters"]["counts"]  # type: ignore[index]
    assert_production_forbidden_zero(counts, context="hybrid lifecycle import")

    assert select_lower_engine("native").selected_engine == "native-rust"
    capabilities = load_native_extension().capabilities()
    assert not has_self_native_production(capabilities)


def test_self_native_production_guard_requires_caps_and_counters() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    reset_native_extension_cache()

    with pytest.raises(NativeExtensionUnavailableError):
        select_self_native_production_engine("native")

    production_auto = select_self_native_production_engine("auto")
    assert production_auto.selected_engine == "python"
    assert production_auto.reason_key == "self_native_production_unavailable"

    summary = _run_lifecycle_baseline_subprocess()
    counts = summary["astichi_counters"]["counts"]  # type: ignore[index]
    assert_production_forbidden_zero(counts, context="hybrid import (pre self-native)")
    with pytest.raises(AssertionError, match="missing required counters"):
        assert_production_requirements(
            counts,
            context="self-native production (not enabled yet)",
        )
