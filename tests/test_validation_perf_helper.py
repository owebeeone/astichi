from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType


def _load_lifecycle_perf_helper() -> ModuleType:
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


def test_lifecycle_perf_helper_configures_engine_environment(monkeypatch) -> None:
    helper = _load_lifecycle_perf_helper()

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    helper._configure_engine_request("auto")
    assert "ASTICHI_LOWER_ENGINE" not in os.environ

    helper._configure_engine_request("python")
    assert os.environ["ASTICHI_LOWER_ENGINE"] == "python"

    helper._configure_engine_request("native")
    assert os.environ["ASTICHI_LOWER_ENGINE"] == "native"


def test_lifecycle_perf_helper_counter_summary_splits_native_and_hot_counters() -> None:
    helper = _load_lifecycle_perf_helper()

    summary = helper._counter_summary(
        {
            "counts": {
                "native_scope_append_occurrence": 2,
                "rebuild_composable": 3,
                "to_executable_ast": 1,
                "other": 4,
            },
            "seconds": {
                "native_scope_append_occurrence": 0.1,
                "rebuild_composable": 0.2,
                "to_executable_ast": 0.3,
                "other": 0.4,
            },
            "max_seconds": {},
        }
    )

    assert summary["native_counts"] == {"native_scope_append_occurrence": 2}
    assert summary["native_seconds"] == {"native_scope_append_occurrence": 0.1}
    assert summary["hot_counts"]["rebuild_composable"] == 3
    assert summary["hot_counts"]["candidate_lookup_lower"] == 0
    assert summary["hot_seconds"]["to_executable_ast"] == 0.3
    assert summary["top_python_counts"][0] == {"name": "other", "count": 4}
