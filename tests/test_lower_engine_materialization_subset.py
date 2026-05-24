from __future__ import annotations

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_composable,
    as_external_value,
    as_identifier,
    require_one,
)
from astichi.perf_counters import collect_perf_counters


def test_lower_materializes_expression_overlay_subset_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
class class_name__astichi_arg__:
    default = astichi_bind_external(default_value)

result = astichi_hole(value)
""".strip()
        + "\n"
    )
    value = astichi.compile("40 + 2\n")
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
                as_external_value(7),
                name="default_value",
                build_match=("Root",),
                owner_match=("GeneratedClass",),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(value, build_name="Value"),
                name="value",
                build_match=("Root",),
            )
        )
    )

    with collect_perf_counters() as counters:
        lower_source = scope.lower_materialize().emit(provenance=False)

    adapter_source = scope.build().materialize().emit(provenance=False)
    assert lower_source == adapter_source
    assert lower_source == ("class GeneratedClass:\n    default = 7\nresult = 40 + 2\n")
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialize"] == 1
    assert counts["lower_materialization_plan"] == 1
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_block_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("def run():\n    astichi_hole(body)\n")
    body = astichi.compile("result = 1\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(body, build_name="Body"),
                name="body",
                build_match=("Root",),
                owner_match=("run",),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.lower_materialize().emit(provenance=False)

    assert source == "def run():\n    result = 1\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_block_materialization_preserves_edge_order() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("def run():\n    astichi_hole(body)\n")
    first = astichi.compile("result.append('first')\n")
    second = astichi.compile("result.append('second')\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(second, build_name="Second", order=20),
                name="body",
                build_match=("Root",),
                owner_match=("run",),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(first, build_name="First", order=10),
                name="body",
                build_match=("Root",),
                owner_match=("run",),
            )
        )
    )

    assert scope.lower_materialize().emit(provenance=False) == (
        "def run():\n    result.append('first')\n    result.append('second')\n"
    )


def test_lower_materialization_fallback_is_counted_for_unsupported_params() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("def run(value__astichi_param_hole__):\n    pass\n")
    params = astichi.compile("def astichi_params(item):\n    pass\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(params, build_name="Params"),
                name="value",
                build_match=("Root",),
                owner_match=("run",),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.lower_materialize().emit(provenance=False)

    assert source == "def run(item):\n    pass\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_adapter_fallback"] == 1
    assert counts["build_merge"] == 1
    assert counts["materialize_composable"] == 1
