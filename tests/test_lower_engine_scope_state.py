from __future__ import annotations

from pathlib import Path
import sys

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_composable,
    find_candidates,
    require_one,
)
from astichi.structural_snapshot import write_structural_snapshot
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_ACTUAL_STRUCTURAL_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "structural"


def test_scope_lower_occurrence_state_matches_structural_golden() -> None:
    root = astichi.compile("result = astichi_hole(value)\n")
    value = astichi.compile("1\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    scope.apply(
        require_one(
            find_candidates(
                scope.inventory,
                as_composable(value, build_name="Value"),
                name="value",
                build_match=("Root",),
            )
        )
    )

    assert scope.project_lower_inventory() == scope.inventory

    actual_text = write_structural_snapshot(scope.lower_structural_snapshot())

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_lower_occurrence_state.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "scope_lower_occurrence_state.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text
