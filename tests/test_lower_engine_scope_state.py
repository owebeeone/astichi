from __future__ import annotations

from pathlib import Path
import sys

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_composable,
    as_external_value,
    as_identifier,
    require_one,
)
from astichi.assembler.scope import find_candidates_in_inventory
from astichi.structural_snapshot import write_structural_snapshot
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_ACTUAL_STRUCTURAL_DIR = (
    actual_results_dir(
        _PROJECT_ROOT,
        runtime_version=(sys.version_info.major, sys.version_info.minor),
    )
    / "goldens"
    / "structural"
)


def test_scope_lower_occurrence_state_matches_structural_golden() -> None:
    root = astichi.compile("result = astichi_hole(value)\n")
    value = astichi.compile("1\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    resource = as_composable(value, build_name="Value")
    legacy_candidates = find_candidates_in_inventory(
        scope.inventory,
        resource,
        name="value",
        build_match=("Root",),
    )
    lower_candidates = scope.find_candidates(
        resource,
        name="value",
        build_match=("Root",),
    )
    assert lower_candidates == legacy_candidates

    scope.apply(require_one(lower_candidates))

    assert scope.project_lower_inventory() == scope.inventory

    actual_text = write_structural_snapshot(scope.lower_structural_snapshot())

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "scope_lower_occurrence_state.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "scope_lower_occurrence_state.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_scope_lower_candidate_lookup_matches_legacy_for_bindings() -> None:
    root = astichi.compile(
        """
class class_name__astichi_arg__:
    default = astichi_bind_external(default_value)
"""
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    for resource, name in (
        (as_identifier("Generated"), "class_name"),
        (as_external_value(1), "default_value"),
    ):
        legacy_candidates = find_candidates_in_inventory(
            scope.inventory,
            resource,
            name=name,
            build_match=("Root",),
        )
        lower_candidates = scope.find_candidates(
            resource,
            name=name,
            build_match=("Root",),
        )
        assert lower_candidates == legacy_candidates


def test_identifier_overlay_resolves_later_owner_selectors() -> None:
    root = astichi.compile(
        """
class class_name__astichi_arg__:
    def method_name__astichi_arg__(self):
        astichi_hole(body)
"""
    )
    body = astichi.compile("value = 1\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)

    scope.apply(
        require_one(
            scope.find_candidates(
                as_identifier("GeneratedClass"),
                name="class_name",
                build_match=("Root",),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_identifier("run"),
                name="method_name",
                build_match=("Root",),
                owner_match=("GeneratedClass",),
            )
        )
    )
    body_candidates = scope.find_candidates(
        as_composable(body, build_name="Body"),
        name="body",
        build_match=("Root",),
        owner_match=("GeneratedClass", "run"),
    )

    assert len(body_candidates) == 1
    assert body_candidates[0].target_record.code_owner.nodes[0].logical_name() == (
        "GeneratedClass"
    )
    assert body_candidates[0].target_record.code_owner.nodes[1].logical_name() == "run"


def test_identifier_overlay_state_matches_structural_golden() -> None:
    root = astichi.compile(
        """
class class_name__astichi_arg__:
    default = astichi_bind_external(default_value)
"""
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_identifier("GeneratedClass"),
                name="class_name",
                build_match=("Root",),
            )
        )
    )

    projected = scope.project_lower_inventory()
    external_record = projected.records_for_ids(
        projected.port_record_ids("default_value")
    )[0]
    assert external_record.code_owner.nodes[0].logical_name() == "GeneratedClass"
    actual_text = write_structural_snapshot(scope.lower_structural_snapshot())

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "identifier_overlay_state.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "identifier_overlay_state.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text
