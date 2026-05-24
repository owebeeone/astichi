from __future__ import annotations

from pathlib import Path
import sys

import astichi
from astichi.lower_engine import (
    LowerEngine,
    LowerTemplateBinding,
    LowerTemplateCache,
    copy_composable_executable_ast,
    copy_composable_template_ast,
    render_composable_source,
)
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


def test_template_binding_rebinds_into_shared_lower_engine() -> None:
    root = astichi.compile("result = astichi_hole(value)\n")
    value = astichi.compile("1\n")
    assert isinstance(root._lower_template, LowerTemplateBinding)
    assert isinstance(value._lower_template, LowerTemplateBinding)
    engine = LowerEngine()
    cache = LowerTemplateCache(engine)

    root_template = cache.template_id_for(root._lower_template)
    value_template = cache.template_id_for(value._lower_template)
    assert cache.template_id_for(root._lower_template) == root_template

    state = engine.new_state()
    engine.append_occurrence(state, root_template, build_path=("Root",))
    engine.append_occurrence(state, value_template, build_path=("Value",))
    actual_text = write_structural_snapshot(engine.structural_snapshot(state))

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "shared_template_registration.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "shared_template_registration.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_explicit_facade_artifact_copy_apis_return_caller_owned_artifacts() -> None:
    composable = astichi.compile("result = 1\n")

    template_ast = copy_composable_template_ast(composable)
    executable_ast = copy_composable_executable_ast(composable)
    source = render_composable_source(composable, provenance=False)

    assert template_ast is not composable.tree
    assert executable_ast is not composable.tree
    assert source == "result = 1\n"
