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
    materialized = (
        counts.get("lower_materialization_plan", 0)
        + counts.get("native_materialize_operation_stream", 0)
    )
    if counts.get("copy_python_ast", 0) and materialized == 0:
        materialized = 1
    assert materialized == 1
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("rebuild_composable", 0) == 0
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


def test_lower_materializes_unfilled_defaulted_block_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def run():
    with astichi_hole(body) as astichi_fallback:
        return 1
""".strip()
        + "\n"
    )
    scope.add("Root", root)

    with collect_perf_counters() as counters:
        source = scope.lower_materialize().emit(provenance=False)

    assert source == "def run():\n    return 1\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_block_materialization_preserves_edge_order() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("def run():\n    astichi_hole(body)\n")
    first = astichi.compile("0\n")
    second = astichi.compile("1\n")
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

    assert (
        scope.lower_materialize().emit(provenance=False) == "def run():\n    0\n    1\n"
    )


def test_scope_build_selects_lower_materialization_for_supported_subset() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("result = astichi_hole(value)\n")
    value = astichi.compile("42\n")
    scope.add("Root", root)
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
        source = scope.build().materialize().emit(provenance=False)

    assert source == "result = 42\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_build_selection"] == 1
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0


def test_lower_materializes_parameters_without_builder_merge() -> None:
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
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_scope_build_selects_lower_materialization_for_parameters() -> None:
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
        source = scope.build().materialize().emit(provenance=False)

    assert source == "def run(item):\n    pass\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_build_selection"] == 1
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0


def test_lower_materializes_static_pyimport_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        "astichi_pyimport(module=foo, names=(a, b))\nresult = a + b\n"
    )
    scope.add("Root", root)

    with collect_perf_counters() as counters:
        source = scope.lower_materialize().emit(provenance=False)

    assert source == "from foo import a, b\nresult = a + b\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_pyimport_name_collision_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("astichi_pyimport(module=foo, names=(a,))\na = 1\n")
    scope.add("Root", root)

    with collect_perf_counters() as counters:
        source = scope.build().emit(provenance=False)

    assert source == "from foo import a\na__astichi_scoped_1 = 1\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_boundary_markers_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def run():
    items = []
    exported = []
    astichi_hole(body)
    return items, exported
""".strip()
        + "\n"
    )
    body = astichi.compile(
        """
astichi_import(items)
items.append(1)
astichi_pass(exported).append(2)
value = 3
astichi_export(value)
""".strip()
        + "\n"
    )
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

    assert source == (
        "def run():\n"
        "    items = []\n"
        "    exported = []\n"
        "    items.append(1)\n"
        "    exported.append(2)\n"
        "    value = 3\n"
        "    return (items, exported)\n"
    )
    namespace: dict[str, object] = {}
    exec(source, namespace)
    assert namespace["run"]() == ([1], [2])  # type: ignore[operator]
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_renames_colliding_block_locals_and_strips_keep() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def run():
    value = 1
    astichi_keep(value)
    astichi_hole(body)
    return value
""".strip()
        + "\n"
    )
    body = astichi.compile("value = 2\nseen = value\n")
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

    assert source == (
        "def run():\n"
        "    value = 1\n"
        "    value__astichi_scoped_1 = 2\n"
        "    seen = value__astichi_scoped_1\n"
        "    return value\n"
    )
    assert "astichi_keep" not in source
    namespace: dict[str, object] = {}
    exec(source, namespace)
    assert namespace["run"]() == 1  # type: ignore[operator]
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_elif_clauses_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def dispatch(kind):
    if kind == "base":
        return "base"
    elif astichi_elif(branches):
        pass
    else:
        return "fallback"
""".strip()
        + "\n"
    )
    create = astichi.compile(
        """
def astichi_elif():
    if kind == "create":
        return "created"
""".strip()
        + "\n"
    )
    delete = astichi.compile(
        """
def astichi_elif():
    if kind == "delete":
        return "deleted"
""".strip()
        + "\n"
    )
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(delete, build_name="Delete", order=20),
                name="branches",
                build_match=("Root",),
                owner_match=("dispatch",),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(create, build_name="Create", order=10),
                name="branches",
                build_match=("Root",),
                owner_match=("dispatch",),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.lower_materialize().emit(provenance=False)

    assert source == (
        "def dispatch(kind):\n"
        "    if kind == 'base':\n"
        "        return 'base'\n"
        "    elif kind == 'create':\n"
        "        return 'created'\n"
        "    elif kind == 'delete':\n"
        "        return 'deleted'\n"
        "    else:\n"
        "        return 'fallback'\n"
    )
    namespace: dict[str, object] = {}
    exec(source, namespace)
    dispatch = namespace["dispatch"]
    assert dispatch("create") == "created"  # type: ignore[operator]
    assert dispatch("delete") == "deleted"  # type: ignore[operator]
    assert dispatch("base") == "base"  # type: ignore[operator]
    assert dispatch("other") == "fallback"  # type: ignore[operator]
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_boundary_elif_payloads_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        """
def dispatch(kind):
    if kind == "base":
        return "base"
    elif astichi_elif(branches):
        pass
""".strip()
        + "\n"
    )
    create = astichi.compile(
        """
astichi_keep(kind)
def astichi_elif():
    astichi_import(kind)
    if kind == "create":
        return "created"
""".strip()
        + "\n"
    )
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(create, build_name="Create"),
                name="branches",
                build_match=("Root",),
                owner_match=("dispatch",),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.build().emit(provenance=False)

    assert "elif kind == 'create':" in source
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_starred_funcargs_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("result = func(*astichi_hole(args))\n")
    args = astichi.compile("astichi_funcargs(1)\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(args, build_name="Args"),
                name="args",
                build_match=("Root",),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.build().emit(provenance=False)

    assert source == "result = func(1)\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_starred_expression_arg_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("result = func(*astichi_hole(args))\n")
    arg = astichi.compile("value\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(arg, build_name="Arg"),
                name="args",
                build_match=("Root",),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.build().emit(provenance=False)

    assert source == "result = func(value)\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_starred_tuple_expression_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("values = (*astichi_hole(items),)\n")
    item = astichi.compile('"slot_name"\n')
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(item, build_name="Item"),
                name="items",
                build_match=("Root",),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.build().emit(provenance=False)

    assert source == "values = ('slot_name',)\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_nested_occurrences_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("def build():\n    astichi_hole(body)\n")
    class_body = astichi.compile(
        """
class class_name__astichi_arg__:
    values = (*astichi_hole(items),)

    def __init__(self, params__astichi_param_hole__):
        astichi_hole(init_body)
""".strip()
        + "\n"
    )
    item = astichi.compile('"slot_name"\n')
    params = astichi.compile('def astichi_params(*, name="default"):\n    pass\n')
    init_body = astichi.compile("self.name = name\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(class_body, build_name="Class"),
                name="body",
                build_match=("Root",),
                owner_match=("build",),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_identifier("Generated"),
                name="class_name",
                build_match=("Root", "Class"),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(item, build_name="Item"),
                name="items",
                build_match=("Root", "Class"),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(params, build_name="Params"),
                name="params",
                build_match=("Root", "Class"),
            )
        )
    )
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(init_body, build_name="InitBody"),
                name="init_body",
                build_match=("Root", "Class"),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.build().emit(provenance=False)

    assert source == (
        "def build():\n"
        "\n"
        "    class Generated:\n"
        "        values = ('slot_name',)\n\n"
        "        def __init__(self, *, name='default'):\n"
        "            self.name = name\n"
    )
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("builder_adapter_mutation", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0


def test_lower_materializes_dstar_funcargs_without_builder_merge() -> None:
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("result = func(**astichi_hole(kwargs))\n")
    kwargs = astichi.compile("astichi_funcargs(named=value, **extra)\n")
    scope.add("Root", root)
    scope.apply(
        require_one(
            scope.find_candidates(
                as_composable(kwargs, build_name="Kwargs"),
                name="kwargs",
                build_match=("Root",),
            )
        )
    )

    with collect_perf_counters() as counters:
        source = scope.build().emit(provenance=False)

    assert source == "result = func(named=value, **extra)\n"
    counts = counters.snapshot()["counts"]
    assert counts["lower_materialization_artifact"] == 1
    assert counts.get("lower_materialization_adapter_fallback", 0) == 0
    assert counts.get("build_merge", 0) == 0
    assert counts.get("materialize_composable", 0) == 0
