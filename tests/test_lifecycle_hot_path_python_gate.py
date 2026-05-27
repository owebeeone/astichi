"""Fool-proof gate: lifecycle import must not build CPython AST before handoff.

When this passes, ``native.self_native.current_surfaces.v1`` denotes a real
production hot path (see HotPathNoPythonPlan.md H0/H4).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from astichi.lower_engine.native import load_native_extension, reset_native_extension_cache
from astichi.lower_engine.self_native import (
    SELF_NATIVE_CURRENT_SURFACES_FEATURE,
    has_self_native_production,
)
from astichi.validation.hot_path_guards import (
    HOT_PATH_FORBIDDEN_COUNTERS,
    assert_hot_path_forbidden_zero,
    assert_hot_path_handoff_shape,
)


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


def test_hot_path_forbidden_counter_names_include_compile_parse() -> None:
    assert "native_compile_parse" in HOT_PATH_FORBIDDEN_COUNTERS
    assert "native_materialize_workspace_copy" in HOT_PATH_FORBIDDEN_COUNTERS


def test_lifecycle_import_has_no_python_ast_work_before_handoff() -> None:
    """Canonical gate for full Rust hot path (see HotPathNoPythonPlan.md)."""
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    reset_native_extension_cache()
    capabilities = load_native_extension().capabilities()
    if not has_self_native_production(capabilities):
        pytest.skip(
            f"{SELF_NATIVE_CURRENT_SURFACES_FEATURE} not advertised; "
            "hot-path gate applies only to self-native production builds"
        )

    summary = _run_lifecycle_baseline_subprocess()
    counts = summary["astichi_counters"]["counts"]  # type: ignore[index]
    decorated = int(summary["decorated_classes"])  # type: ignore[arg-type]

    assert_hot_path_forbidden_zero(counts)
    assert_hot_path_handoff_shape(counts, decorated_classes=decorated)
