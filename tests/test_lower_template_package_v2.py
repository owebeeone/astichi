from __future__ import annotations

import ast
from pathlib import Path
import sys

import pytest

from astichi.lower_engine import (
    LowerEngine,
    LowerTemplatePackageV2,
    PackageSchemaMismatchError,
    PackageSnapshotFormatError,
    extract_scope_specs,
    round_trip_package_snapshot_text,
    write_package_snapshot,
)
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_GOLDENS_DIR = data_golden_dir(
    _PROJECT_ROOT,
    phase="lower_template_package_v2",
)
_ACTUAL_PACKAGE_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "lower_template_package_v2"


def test_empty_package_snapshot_matches_golden() -> None:
    package = LowerTemplatePackageV2(
        template_key="empty_template",
        source_summary="pass",
    )

    _assert_package_snapshot_matches_golden(package, "empty_package.json")


def test_populated_package_snapshot_matches_golden() -> None:
    package = _populated_package()

    _assert_package_snapshot_matches_golden(package, "populated_package.json")
    assert [segment.snapshot() for segment in package.ast_path_segments(0)] == [
        {"field": "body", "index": 0},
        {"field": "value", "index": None},
    ]
    assert [record.template_record_id for record in package.records_by_owner_path(("Root",))] == [
        0
    ]
    assert package.structural_template_snapshot(template_id=0) == {
        "record_count": 1,
        "source_summary": "result = astichi_hole(value)",
        "template_id": 0,
        "template_key": "expression_template",
    }
    assert package.structural_locator_snapshots(template_id=0) == [
        {
            "ast_path": "body[0].value",
            "authored_summary": "astichi_hole(value)",
            "locator_id": 0,
            "materialization_anchor": "replace-expression",
            "parent_locator_id": None,
            "role_key": "expression.hole",
            "template_id": 0,
        }
    ]
    assert package.structural_record_snapshot(
        template_record_id=0,
        occurrence_id=0,
        visible=True,
        satisfied=False,
    ) == {
        "code_owner": ["Root"],
        "inventory_kind": "expression.hole",
        "locator_id": 0,
        "occurrence_id": 0,
        "record_id": [0, 0],
        "resource_name": "value",
        "semantic_summary": "expression hole value",
        "state": {"satisfied": False, "visible": True},
        "surface_key": "expression.hole",
        "template_record_id": 0,
    }


def test_scope_extraction_package_snapshot_matches_golden() -> None:
    tree = ast.parse(
        """
class Box:
    def make(self):
        async def load():
            return 1
        return load

async def outer():
    return 2
"""
    )
    engine = LowerEngine()
    template_id = engine.register_template(
        template_key="scope_template",
        source_summary="nested scope source",
        records=(),
        scopes=extract_scope_specs(tree),
    )

    _assert_package_snapshot_matches_golden(
        engine.template_package(template_id),
        "scope_package.json",
    )


def test_package_intern_ids_are_package_local() -> None:
    first = LowerTemplatePackageV2(template_key="one", source_summary="same")
    second = LowerTemplatePackageV2(template_key="two", source_summary="same")

    assert first.intern_string("local") == 3
    assert second.intern_string("local") == 3


def test_package_snapshot_rejects_unknown_schema() -> None:
    package = LowerTemplatePackageV2(
        template_key="empty_template",
        source_summary="pass",
    )
    snapshot = package.snapshot()
    snapshot["schema"] = "astichi.lower-template-package.v3"

    with pytest.raises(
        PackageSchemaMismatchError,
        match="unsupported package snapshot schema",
    ):
        write_package_snapshot(snapshot)


def test_package_snapshot_rejects_unstable_strings() -> None:
    package = LowerTemplatePackageV2(
        template_key="/tmp/local.py",
        source_summary="pass",
    )

    with pytest.raises(PackageSnapshotFormatError, match="absolute path"):
        write_package_snapshot(package.snapshot())


def _assert_package_snapshot_matches_golden(
    package: LowerTemplatePackageV2,
    golden_name: str,
) -> None:
    actual_text = write_package_snapshot(package.snapshot())
    assert round_trip_package_snapshot_text(actual_text) == actual_text

    _ACTUAL_PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_PACKAGE_DIR / golden_name
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (_PACKAGE_GOLDENS_DIR / golden_name).read_text(encoding="utf-8")
    assert actual_text == expected_text


def _populated_package() -> LowerTemplatePackageV2:
    package = LowerTemplatePackageV2(
        template_key="expression_template",
        source_summary="result = astichi_hole(value)",
        surface_bundle_signature="astichi.current",
    )
    locator_id = package.add_locator(
        ast_path="body[0].value",
        role_key="expression.hole",
        authored_summary="astichi_hole(value)",
        materialization_anchor="replace-expression",
    )
    package.add_record(
        surface_key="expression.hole",
        operation_key="insert.expression",
        locator_id=locator_id,
        resource_name="value",
        inventory_kind="expression.hole",
        owner_path=("Root",),
        semantic_summary="expression hole value",
    )
    package.add_scope(
        scope_kind="module",
        ast_path="",
        owner_path=("Root",),
        local_bindings=("result",),
    )
    return package
