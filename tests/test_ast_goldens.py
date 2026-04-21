from __future__ import annotations

import ast
from pathlib import Path
import sys

import pytest

from astichi.emit import verify_round_trip
from tests.versioned_test_harness import (
    actual_results_dir,
    data_golden_dir,
    data_gold_src_dir,
    discover_golden_cases,
    run_golden_case,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GOLD_SRC_DIR = data_gold_src_dir(_PROJECT_ROOT)
_PRE_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="pre_materialized")
_MATERIALIZED_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="materialized")
_ACTUAL_GOLDENS_ROOT = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens"

_CASES = discover_golden_cases(_PROJECT_ROOT)


def test_golden_fixture_sets_match() -> None:
    source_names = {path.name for path in _GOLD_SRC_DIR.glob("*.py")}
    pre_names = {path.name for path in _PRE_GOLDENS_DIR.glob("*.py")}
    materialized_names = {path.name for path in _MATERIALIZED_GOLDENS_DIR.glob("*.py")}

    assert source_names
    assert pre_names == source_names
    assert materialized_names == source_names


@pytest.mark.parametrize("case_name", _CASES)
def test_fixture_outputs_match_goldens(case_name: str) -> None:
    actual_pre = _ACTUAL_GOLDENS_ROOT / "pre_materialized" / case_name
    actual_materialized = _ACTUAL_GOLDENS_ROOT / "materialized" / case_name
    actual_pre.parent.mkdir(parents=True, exist_ok=True)
    actual_materialized.parent.mkdir(parents=True, exist_ok=True)

    completed = run_golden_case(
        _GOLD_SRC_DIR / case_name,
        actual_pre,
        actual_materialized,
        cwd=_PROJECT_ROOT,
        check=False,
    )
    assert completed.returncode == 0, (
        f"{case_name} failed with exit code {completed.returncode}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    assert actual_pre.exists()
    assert actual_materialized.exists()

    pre_source = actual_pre.read_text(encoding="utf-8")
    materialized_source = actual_materialized.read_text(encoding="utf-8")
    expected_pre_source = (_PRE_GOLDENS_DIR / case_name).read_text(encoding="utf-8")
    expected_materialized_source = (
        _MATERIALIZED_GOLDENS_DIR / case_name
    ).read_text(encoding="utf-8")

    assert "# astichi-provenance: " in pre_source
    assert "# astichi-provenance: " in expected_pre_source
    assert "# astichi-provenance: " not in materialized_source
    assert "# astichi-provenance: " not in expected_materialized_source
    verify_round_trip(pre_source)
    verify_round_trip(expected_pre_source)
    ast.parse(pre_source, filename=f"goldens/pre_materialized/{case_name}")
    compile(materialized_source, f"goldens/materialized/{case_name}", "exec")

    assert _normalize_provenance_payload(pre_source) == _normalize_provenance_payload(
        expected_pre_source
    )
    assert materialized_source == expected_materialized_source


def _normalize_provenance_payload(source: str) -> str:
    lines = source.splitlines()
    return "\n".join(
        "# astichi-provenance: <payload>"
        if line.startswith("# astichi-provenance: ")
        else line
        for line in lines
    ) + ("\n" if source.endswith("\n") else "")
