from __future__ import annotations

import ast
from pathlib import Path
import sys

import pytest

from astichi.assembler.scope import (
    _lower_boundary_available_names,
    _lower_boundary_marker_tuple_supported,
    _lower_pyimport_existing_binding_names,
    _lower_scope_binding_names,
)
from astichi.lowering import recognize_markers
from astichi.lower_engine import (
    LowerEngine,
    LowerTemplatePackageV2,
    PackageSchemaMismatchError,
    PackageSnapshotFormatError,
    extract_marker_specs,
    extract_pyimport_marker_specs,
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


def test_binding_extraction_package_snapshot_matches_golden() -> None:
    tree = ast.parse(
        """
import os
from pkg import thing as alias
value = 1
del stale
for item in items:
    loop_value = item

class Box:
    import math as m
    field = 1

    def make(self, x, *args, y, **kw):
        local = x
        del old
        import json as js
        for child in args:
            pass

        def helper():
            return local

        class Inner:
            pass

        return child
"""
    )
    scope_specs = extract_scope_specs(tree)
    engine = LowerEngine()
    template_id = engine.register_template(
        template_key="binding_scope_template",
        source_summary="binding scope source",
        records=(),
        scopes=scope_specs,
    )

    specs_by_owner = {spec.owner_path: spec for spec in scope_specs}
    assert frozenset(specs_by_owner[()].local_bindings) == _lower_scope_binding_names(
        tree
    )
    assert frozenset(
        specs_by_owner[("Box",)].local_bindings
    ) == _lower_scope_binding_names(tree.body[5])
    assert frozenset(
        specs_by_owner[("Box", "make")].local_bindings
    ) == _lower_scope_binding_names(tree.body[5].body[2])
    assert specs_by_owner[("Box", "make")].arguments == (
        "args",
        "kw",
        "self",
        "x",
        "y",
    )

    _assert_package_snapshot_matches_golden(
        engine.template_package(template_id),
        "binding_scope_package.json",
    )
    package = engine.template_package(template_id)
    assert "binding_indexes" not in package.snapshot()
    assert package.scope_ids_for_owner_path(("Box", "make")) == (2,)
    assert package.binding_names_for_scope_id(2) == _lower_scope_binding_names(
        tree.body[5].body[2]
    )
    assert package.argument_names_for_scope_id(2) == frozenset(
        ("args", "kw", "self", "x", "y")
    )
    assert package.boundary_available_names_for_statement_path(
        "body[5]/body[2]/body[6]"
    ) == _lower_boundary_available_names(tree, "body[5]/body[2]/body[6]")
    assert package.pyimport_existing_binding_names() == frozenset(
        _lower_pyimport_existing_binding_names(tree)
    )


def test_marker_ordering_package_snapshot_matches_golden() -> None:
    tree = ast.parse(
        """
astichi_keep(top)

class Box:
    astichi_keep(box)

    def make(self):
        astichi_keep(method)
        return astichi_ref(external=dependency)
"""
    )
    scope_specs = extract_scope_specs(tree)
    engine = LowerEngine()
    template_id = engine.register_template(
        template_key="marker_order_template",
        source_summary="marker order source",
        records=(),
        scopes=scope_specs,
        markers=extract_marker_specs(tree, scope_specs),
    )
    package = engine.template_package(template_id)

    assert package.marker_ids_by_kind("keep") == (0, 1, 2)
    assert package.marker_ids_by_kind("ref") == (3,)
    assert package.marker_ids_by_scope_id(0) == (0,)
    assert package.marker_ids_by_scope_id(1) == (1,)
    assert package.marker_ids_by_scope_id(2) == (2, 3)
    assert [row.source_order for row in package.markers] == [0, 1, 2, 3]
    _assert_package_snapshot_matches_golden(
        package,
        "marker_order_package.json",
    )


def test_boundary_marker_package_snapshot_matches_golden() -> None:
    tree = ast.parse(
        """
astichi_import(inbound, bound=True)
astichi_export(outbound)
value = astichi_pass(shared, outer_bind=True)
"""
    )
    scope_specs = extract_scope_specs(tree)
    engine = LowerEngine()
    template_id = engine.register_template(
        template_key="boundary_marker_template",
        source_summary="boundary marker source",
        records=(),
        scopes=scope_specs,
        markers=extract_marker_specs(tree, scope_specs),
    )
    package = engine.template_package(template_id)

    import_marker = package.markers[0]
    pass_marker = package.markers[2]
    assert "explicit_bind_enabled" in import_marker.flags
    assert "outer_bind_enabled" in pass_marker.flags
    assert package.boundary_markers_supported(frozenset())
    assert package.boundary_markers_supported(
        frozenset(),
        scope_id=0,
    ) == _lower_boundary_marker_tuple_supported(
        recognize_markers(tree),
        frozenset(),
    )

    unresolved_tree = ast.parse("astichi_import(missing)\n")
    unresolved_scope_specs = extract_scope_specs(unresolved_tree)
    unresolved_package_id = engine.register_template(
        template_key="boundary_unresolved_template",
        source_summary="boundary unresolved source",
        records=(),
        scopes=unresolved_scope_specs,
        markers=extract_marker_specs(unresolved_tree, unresolved_scope_specs),
    )
    unresolved_package = engine.template_package(unresolved_package_id)
    assert not unresolved_package.boundary_markers_supported(frozenset())
    assert unresolved_package.boundary_markers_supported(frozenset({"missing"}))

    _assert_package_snapshot_matches_golden(
        package,
        "boundary_marker_package.json",
    )


def test_keep_and_pyimport_package_snapshot_matches_golden() -> None:
    tree = ast.parse(
        """
astichi_keep(module_name)
astichi_pyimport(module=foo, names=(a, b))
astichi_pyimport(module=numpy, as_=np)
astichi_pyimport(module=os)
"""
    )
    scope_specs = extract_scope_specs(tree)
    engine = LowerEngine()
    template_id = engine.register_template(
        template_key="keep_pyimport_template",
        source_summary="keep pyimport source",
        records=(),
        scopes=scope_specs,
        markers=extract_marker_specs(tree, scope_specs),
        pyimport_markers=extract_pyimport_marker_specs(tree),
    )
    package = engine.template_package(template_id)

    assert package.marker_ids_by_kind("keep") == (0,)
    assert package.marker_ids_by_kind("pyimport") == (1, 2, 3)
    assert [row.marker_id for row in package.pyimport_markers] == [1, 2, 3]
    assert package.pyimport_markers[0].flags == ("from_import",)
    assert package.pyimport_markers[1].flags == ("plain_import",)
    assert package.pyimport_markers[2].flags == ("plain_import",)
    _assert_package_snapshot_matches_golden(
        package,
        "keep_pyimport_package.json",
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
