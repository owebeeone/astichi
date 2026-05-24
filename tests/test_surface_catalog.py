from __future__ import annotations

from pathlib import Path
import sys

from astichi.lower_engine import LowerEngine, current_surface_bundle_spec
from astichi.structural_snapshot import write_structural_snapshot
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_ACTUAL_STRUCTURAL_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "structural"

_EXPECTED_CURRENT_PATTERNS = {
    "astichi.pattern.arg.param_hole_suffix",
    "astichi.pattern.attr.ref_sentinel",
    "astichi.pattern.call.bind_external",
    "astichi.pattern.call.comment",
    "astichi.pattern.call.elif_target",
    "astichi.pattern.call.export",
    "astichi.pattern.call.for_iter",
    "astichi.pattern.call.funcargs_payload",
    "astichi.pattern.call.hole",
    "astichi.pattern.call.import",
    "astichi.pattern.call.insert_expr",
    "astichi.pattern.call.keep",
    "astichi.pattern.call.pass",
    "astichi.pattern.call.pyimport",
    "astichi.pattern.call.ref_value",
    "astichi.pattern.decorator.insert_block",
    "astichi.pattern.decorator.insert_elif",
    "astichi.pattern.decorator.insert_params",
    "astichi.pattern.def.elif_payload",
    "astichi.pattern.def.params_payload",
    "astichi.pattern.funcargs.directive_item",
    "astichi.pattern.funcargs.doublestar_item",
    "astichi.pattern.funcargs.keyword_item",
    "astichi.pattern.funcargs.positional_item",
    "astichi.pattern.funcargs.starred_item",
    "astichi.pattern.prefix.expression_payload",
    "astichi.pattern.prefix.pyimport_scope",
    "astichi.pattern.reserved.bind_once",
    "astichi.pattern.reserved.bind_shared",
    "astichi.pattern.suffix.arg_identifier.definition",
    "astichi.pattern.suffix.arg_identifier.import",
    "astichi.pattern.suffix.arg_identifier.keyword",
    "astichi.pattern.suffix.arg_identifier.name",
    "astichi.pattern.suffix.keep_identifier",
    "astichi.pattern.with.defaulted_block_hole",
}


def test_current_surface_catalog_registers_all_current_patterns() -> None:
    registry = LowerEngine().surface_registry
    registered = registry.register_bundle(current_surface_bundle_spec())

    pattern_keys = {pattern.pattern_key for pattern in registered.patterns}

    assert pattern_keys == _EXPECTED_CURRENT_PATTERNS
    assert all(pattern.handle is not None for pattern in registered.patterns)
    assert all(pattern.template_key for pattern in registered.patterns)
    assert all(pattern.operation_key for pattern in registered.patterns)
    assert {
        pattern.pattern_key
        for pattern in registered.patterns
        if pattern.diagnostic_only
    } == {
        "astichi.pattern.reserved.bind_once",
        "astichi.pattern.reserved.bind_shared",
    }


def test_current_surface_catalog_matches_structural_golden() -> None:
    registry = LowerEngine().surface_registry
    registry.register_bundle(current_surface_bundle_spec())

    actual_text = write_structural_snapshot(registry.structural_snapshot())

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "registry_current_patterns.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "registry_current_patterns.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text
