from __future__ import annotations

from pathlib import Path
import sys

import astichi
from astichi.lower_engine import LowerTemplateBinding
from astichi.structural_snapshot import write_structural_snapshot
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_ACTUAL_STRUCTURAL_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "structural"


def test_compile_registers_lower_template_metadata() -> None:
    composable = astichi.compile(
        """
result = astichi_hole(value)
"""
    )

    lower_template = composable._lower_template

    assert isinstance(lower_template, LowerTemplateBinding)
    assert lower_template.surface_bundle_signature
    assert [
        spec.surface_key for spec in lower_template.record_specs
    ] == [
        "astichi.surface.expression.hole",
        "astichi.surface.block.production",
    ]
    assert all(spec.surface_id is not None for spec in lower_template.record_specs)


def test_compile_lower_template_metadata_matches_structural_golden() -> None:
    composable = astichi.compile(
        """
def make():
    value = astichi_bind_external(default)
    return astichi_hole(result)
"""
    )
    lower_template = composable._lower_template
    assert isinstance(lower_template, LowerTemplateBinding)

    actual_text = write_structural_snapshot(lower_template.structural_snapshot())

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "compile_template_metadata.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "compile_template_metadata.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text
