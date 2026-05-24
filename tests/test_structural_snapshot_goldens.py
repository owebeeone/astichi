from __future__ import annotations

from pathlib import Path
import sys

import pytest

from astichi.structural_snapshot import (
    read_structural_snapshot,
    write_structural_snapshot,
)
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_ACTUAL_STRUCTURAL_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "structural"

_EXPECTED_INITIAL_GOLDENS = {
    "external_bind_overlay.json",
    "identifier_bind_overlay.json",
    "lower_engine_tiny_state.json",
    "registry_minimal_bundle.json",
    "scalar_expression_insert.json",
}
_STRUCTURAL_GOLDENS = tuple(sorted(_STRUCTURAL_GOLDENS_DIR.glob("*.json")))


def test_structural_golden_fixture_set_has_initial_cases() -> None:
    assert {path.name for path in _STRUCTURAL_GOLDENS} >= _EXPECTED_INITIAL_GOLDENS


@pytest.mark.parametrize("golden_path", _STRUCTURAL_GOLDENS, ids=lambda path: path.name)
def test_structural_snapshot_goldens_round_trip(golden_path: Path) -> None:
    expected_text = golden_path.read_text(encoding="utf-8")

    snapshot = read_structural_snapshot(expected_text)
    actual_text = write_structural_snapshot(snapshot)

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    (_ACTUAL_STRUCTURAL_DIR / golden_path.name).write_text(
        actual_text,
        encoding="utf-8",
    )
    assert actual_text == expected_text
