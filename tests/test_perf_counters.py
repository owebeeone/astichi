from __future__ import annotations

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_external_value,
    as_identifier,
    require_one,
)
from astichi.perf_counters import collect_perf_counters


def test_perf_counters_collect_assembly_hot_path_counts() -> None:
    root = astichi.compile("value = astichi_bind_external(value)\n")
    scope = AssemblyScope(astichi.build())

    with collect_perf_counters() as counters:
        scope.add("Root", root)
        candidate = require_one(
            scope.find_candidates(
                as_external_value(1),
                name="value",
                build_match=("Root",),
            )
        )
        scope.apply(candidate)
        built = scope.build()
        built.to_executable_ast()

    snapshot = counters.snapshot()
    counts = snapshot["counts"]

    assert counts.get("inventory_projection", 0) == 0
    assert counts.get("replace_occurrence_inventory", 0) == 0
    assert counts.get("debug_inventory_projection", 0) == 0
    assert counts.get("candidate_lookup", 0) == 0
    assert counts["candidate_lookup_lower"] == 1
    assert counts["assembly_scope_apply"] == 1
    assert counts["assembly_scope_apply_external_value"] == 1
    assert counts["rebuild_composable"] == 1
    assert counts["lower_materialization_plan"] == 1
    assert counts["lower_build_selection"] == 1
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("build_merge", 0) == 0
    assert counts["to_executable_ast"] == 1
    assert counts["materialize_composable"] == 1


def test_perf_counters_are_inactive_by_default() -> None:
    scope = AssemblyScope(astichi.build())
    scope.add("Root", astichi.compile("value = 1\n"))

    assert scope.build().materialize().emit(provenance=False) == "value = 1\n"


def test_lower_materialization_plan_counter_is_separate() -> None:
    scope = AssemblyScope(astichi.build())
    scope.add("Root", astichi.compile("value = astichi_bind_external(value)\n"))
    scope.apply(
        require_one(
            scope.find_candidates(
                as_external_value(1),
                name="value",
                build_match=("Root",),
            )
        )
    )

    with collect_perf_counters() as counters:
        scope.lower_materialization_plan()

    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_plan"] == 1
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_external_apply_queues_overlay_without_rebuild() -> None:
    root = astichi.compile("value = astichi_bind_external(value)\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)
    candidate = require_one(
        scope.find_candidates(
            as_external_value(1),
            name="value",
            build_match=("Root",),
        )
    )

    with collect_perf_counters() as counters:
        scope.apply(candidate)

    counts = counters.snapshot()["counts"]
    assert counts["assembly_scope_apply_external_value"] == 1
    assert counts.get("rebuild_composable", 0) == 0


def test_identifier_apply_queues_overlay_without_rebuild() -> None:
    root = astichi.compile("class class_name__astichi_arg__:\n    pass\n")
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)
    candidate = require_one(
        scope.find_candidates(
            as_identifier("Generated"),
            name="class_name",
            build_match=("Root",),
        )
    )

    with collect_perf_counters() as counters:
        scope.apply(candidate)

    counts = counters.snapshot()["counts"]
    assert counts["assembly_scope_apply_identifier_name"] == 1
    assert counts.get("rebuild_composable", 0) == 0
