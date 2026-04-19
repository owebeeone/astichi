from __future__ import annotations

import ast
import textwrap

import pytest

import astichi


def _piece(source: str):
    return astichi.compile(textwrap.dedent(source).strip() + "\n")


def _exec_emitted(composable) -> dict[str, object]:
    source = composable.emit(provenance=False)
    namespace: dict[str, object] = {}
    exec(compile(source, "<test>", "exec"), namespace)  # noqa: S102
    return namespace


def _collect_insert_refs(composable) -> list[str]:
    refs: list[str] = []
    for node in ast.walk(composable.tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Name):
                continue
            if decorator.func.id != "astichi_insert":
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "ref":
                    refs.append(ast.unparse(keyword.value))
    return sorted(refs)


def _prefixed_values(
    namespace: dict[str, object],
    prefix: str,
) -> list[object]:
    return [value for key, value in namespace.items() if key.startswith(prefix)]


def _trace_root_piece():
    return _piece(
        """
        astichi_pass(trace)
        trace = []
        astichi_hole(body)
        result = trace
        """
    )


def _trace_leaf_piece(label: str):
    return _piece(
        f"""
        astichi_import(trace)
        trace.append({label!r})
        """
    )


def _events_root_piece():
    return _piece(
        """
        astichi_pass(events)
        events = []
        astichi_hole(body)
        result = events
        """,
    )


def _loop_piece(domain_source: str, *, bind_external: bool):
    bind_prefix = "astichi_bind_external(DOMAIN)\n" if bind_external else ""
    return _piece(
        f"""
        {bind_prefix}for x in astichi_for({domain_source}):
            astichi_hole(step)
        """
    )


def _ordered_trace(stage_depth: int, first_order: int, second_order: int) -> list[str]:
    assert stage_depth in (1, 2, 3)

    if stage_depth == 1:
        builder = astichi.build()
        builder.add.Root(_trace_root_piece())
        builder.add.First(_trace_leaf_piece("first"))
        builder.add.Second(_trace_leaf_piece("second"))
        builder.Root.body.add.First(order=first_order)
        builder.Root.body.add.Second(order=second_order)
        builder.assign.First.trace.to().Root.trace
        builder.assign.Second.trace.to().Root.trace
        materialized = builder.build().materialize()
        return _exec_emitted(materialized)["result"]

    stage1 = astichi.build()
    stage1.add.Root(_piece("astichi_hole(body)\n"))
    stage1.add.First(_trace_leaf_piece("first"))
    stage1.add.Second(_trace_leaf_piece("second"))
    stage1.Root.body.add.First(order=first_order)
    stage1.Root.body.add.Second(order=second_order)
    built = stage1.build()

    if stage_depth == 2:
        stage2 = astichi.build()
        stage2.add.Root(_trace_root_piece())
        stage2.add.Nested(built)
        stage2.Root.body.add.Nested(order=0)
        stage2.assign.Nested.trace.to().Root.trace
        materialized = stage2.build().materialize()
        return _exec_emitted(materialized)["result"]

    stage2 = astichi.build()
    stage2.add.Middle(_piece("astichi_hole(body)\n"))
    stage2.add.Nested(built)
    stage2.Middle.body.add.Nested(order=0)
    mid_built = stage2.build()

    stage3 = astichi.build()
    stage3.add.Root(_trace_root_piece())
    stage3.add.Pipeline(mid_built)
    stage3.Root.body.add.Pipeline(order=0)
    stage3.assign.Pipeline.trace.to().Root.trace
    materialized = stage3.build().materialize()
    return _exec_emitted(materialized)["result"]


def test_v3_spine_multistage_deep_order_trace() -> None:
    stage1 = astichi.build()
    stage1.add.Root(_piece("astichi_hole(body)\n"))
    stage1.add.First(_trace_leaf_piece("first"))
    stage1.add.Second(_trace_leaf_piece("second"))
    stage1.Root.body.add.First(order=0)
    stage1.Root.body.add.Second(order=0)
    built = stage1.build()

    demand_names = {port.name for port in built.demand_ports}
    assert "trace" in demand_names

    stage2 = astichi.build()
    stage2.add.Root(_trace_root_piece())
    stage2.add.After(_trace_leaf_piece("after"))
    stage2.add.Before(_trace_leaf_piece("before"))
    stage2.add.Nested(built)
    stage2.Root.body.add.After(order=0)
    stage2.Root.body.add.Nested(order=1)
    stage2.Root.body.add.Before(order=2)
    stage2.assign.After.trace.to().Root.trace
    stage2.assign.Before.trace.to().Root.trace
    stage2.assign.Nested.trace.to().Root.trace

    materialized = stage2.build().materialize()
    source = materialized.emit(provenance=False)
    assert "astichi_hole" not in source
    assert "astichi_insert" not in source

    namespace = _exec_emitted(materialized)
    assert namespace["result"] == ["after", "first", "second", "before"]


@pytest.mark.parametrize(
    (
        "domain_source",
        "bind_external",
        "bind_value",
        "unroll_mode",
        "expected_labels",
    ),
    [
        ("DOMAIN", True, (10, 20), "auto", ["first", "second"]),
        ("DOMAIN", True, [7, 9], True, ["first", "second"]),
        ("(1, 2, 3)", False, None, "auto", ["first", "second", "third"]),
    ],
)
def test_v3_late_bind_and_delayed_unroll_matrix(
    domain_source: str,
    bind_external: bool,
    bind_value: object | None,
    unroll_mode: bool | str,
    expected_labels: list[str],
) -> None:
    root_piece = _events_root_piece()
    loop_piece = _loop_piece(domain_source, bind_external=bind_external)

    stage1 = astichi.build()
    stage1.add.Root(root_piece)
    stage1.add.Loop(loop_piece)
    stage1.Root.body.add.Loop(order=0)
    built = stage1.build()

    pipeline_piece = built if bind_value is None else built.bind(DOMAIN=bind_value)

    stage2 = astichi.build()
    stage2.add.Pipeline(pipeline_piece)
    for index, label in enumerate(expected_labels):
        step_name = f"Step{index}"
        getattr(stage2.add, step_name)(_piece(
            f"""
            astichi_import(events)
            events.append({label!r})
            """
        ))
        getattr(stage2.Pipeline.Loop.step[index].add, step_name)(order=index)

    merged = stage2.build(unroll=unroll_mode)
    refs = _collect_insert_refs(merged)
    assert "Loop" in refs
    for index in range(len(expected_labels)):
        assert f"Loop.Step{index}[{index}]" in refs

    materialized = merged.materialize()
    source = materialized.emit(provenance=False)
    assert "astichi_for" not in source

    namespace = _exec_emitted(materialized)
    assert namespace["result"] == expected_labels


def test_v3_spine_stage_built_import_demand_bound_later() -> None:
    stage1 = astichi.build()
    stage1.add.Step(
        _piece(
            """
            astichi_import(counter)
            counter = counter + 2
            """
        )
    )
    built = stage1.build()

    demand_names = {port.name for port in built.demand_ports}
    assert "counter" in demand_names

    stage2 = astichi.build()
    stage2.add.Root(
        _piece(
            """
            astichi_pass(counter)
            counter = 10
            astichi_hole(body)
            result = counter
            """
        )
    )
    stage2.add.StageBuilt(built)
    stage2.Root.body.add.StageBuilt(order=0)
    stage2.assign.StageBuilt.counter.to().Root.counter

    namespace = _exec_emitted(stage2.build().materialize())
    assert namespace["counter"] == 12
    assert namespace["result"] == 12


def test_v3_spine_descendant_ref_paths_survive_stage_boundary() -> None:
    stage1 = astichi.build()
    stage1.add.Root(_piece("astichi_hole(body)\n"))
    stage1.add.Parse(_piece("astichi_hole(body)\n"))
    stage1.add.Normalize(_piece("value = 1\n"))
    stage1.Root.body.add.Parse(order=0)
    stage1.Parse.body.add.Normalize(order=0)
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Outer(_piece("astichi_hole(body)\n"))
    stage2.add.Pipeline(built)
    stage2.Outer.body.add.Pipeline(order=0)
    merged = stage2.build()

    assert _collect_insert_refs(merged) == [
        "Pipeline",
        "Pipeline.Parse",
        "Pipeline.Parse.Normalize",
    ]


def test_v3_spine_descendant_add_and_assign_match_same_shell_path() -> None:
    stage1 = astichi.build()
    stage1.add.Root(_piece("astichi_hole(body)\n"))
    stage1.add.Right(
        _piece(
            """
            astichi_pass(total)
            total = 20
            """
        )
    )
    stage1.add.Left(
        _piece(
            """
            astichi_pass(total)
            total = 10
            """
        )
    )
    stage1.add.Parse(_piece("astichi_hole(body)\n"))
    stage1.Root.body.add.Right(order=0)
    stage1.Root.body.add.Left(order=1)
    stage1.Root.body.add.Parse(order=2)
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pipeline(built)
    stage2.add.Step(
        _piece(
            """
            astichi_import(total)
            step_result = total + 1
            astichi_export(step_result)
            """
        )
    )
    stage2.Pipeline.Parse.body.add.Step(order=0)
    stage2.assign.Step.total.to().Pipeline.Right.total

    merged = stage2.build()
    refs = _collect_insert_refs(merged)
    assert "Parse.Step" in refs
    assert all(not ref.startswith("Left.Step") for ref in refs)
    assert all(not ref.startswith("Right.Step") for ref in refs)

    namespace = _exec_emitted(merged.materialize())
    assert _prefixed_values(namespace, "step_result") == [21]


def test_v3_spine_reuse_same_built_composable_with_distinct_bindings() -> None:
    stage1 = astichi.build()
    stage1.add.Unit(
        _piece(
            """
            astichi_import(counter)
            result = counter + 1
            astichi_export(result)
            """
        )
    )
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.AInit(
        _piece(
            """
            astichi_pass(left_counter)
            left_counter = 10
            """
        )
    )
    stage2.add.BInit(
        _piece(
            """
            astichi_pass(right_counter)
            right_counter = 20
            """
        )
    )
    stage2.add.First(built)
    stage2.add.Second(built)
    stage2.assign.First.counter.to().AInit.left_counter
    stage2.assign.Second.counter.to().BInit.right_counter

    namespace = _exec_emitted(stage2.build().materialize())
    assert sorted(_prefixed_values(namespace, "result")) == [11, 21]


def test_v3_spine_export_survives_stage_boundary() -> None:
    stage1 = astichi.build()
    stage1.add.Exporter(
        _piece(
            """
            value = 42
            astichi_export(value)
            """
        )
    )
    built = stage1.build()

    assert "value" in {port.name for port in built.supply_ports}

    stage2 = astichi.build()
    stage2.add.Pipeline(built)
    reused = stage2.build()

    assert "value" in {port.name for port in reused.supply_ports}

    source = reused.materialize().emit(provenance=False)
    assert "astichi_export" not in source
    assert "value = 42" in source


@pytest.mark.parametrize(
    ("stage_depth", "first_order", "second_order", "expected"),
    [
        (1, 0, 1, ["first", "second"]),
        (2, 1, 0, ["second", "first"]),
        (3, 0, 0, ["first", "second"]),
    ],
)
def test_v3_ordering_matrix(
    stage_depth: int,
    first_order: int,
    second_order: int,
    expected: list[str],
) -> None:
    assert _ordered_trace(stage_depth, first_order, second_order) == expected


def test_v3_identifier_matrix_descendant_source_path_across_stage_boundary() -> None:
    stage1 = astichi.build()
    stage1.add.Root(_piece("astichi_hole(body)\n"))
    stage1.add.Inner(
        _piece(
            """
            astichi_import(counter)
            result = counter + 1
            astichi_export(result)
            """
        )
    )
    stage1.Root.body.add.Inner(order=0)
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Init(
        _piece(
            """
            astichi_pass(counter)
            counter = 10
            """
        )
    )
    stage2.add.Pipeline(built)
    stage2.assign.Pipeline.Inner.counter.to().Init.counter

    namespace = _exec_emitted(stage2.build().materialize())
    assert _prefixed_values(namespace, "result") == [11]


def test_v3_identifier_matrix_forward_declared_deep_target_rejects() -> None:
    stage1 = astichi.build()
    stage1.add.Root(_piece("astichi_hole(body)\n"))
    stage1.add.Right(
        _piece(
            """
            astichi_pass(total)
            total = 20
            """
        )
    )
    stage1.Root.body.add.Right(order=0)
    built = stage1.build()

    builder = astichi.build()
    builder.add.Step(
        _piece(
            """
            astichi_import(total)
            value = total + 1
            """
        )
    )

    with pytest.raises(
        ValueError,
        match=r"assign target path cannot continue after final outer name `Pipeline\.Right`",
    ):
        builder.assign.Step.total.to().Pipeline.Right.total

    builder.add.Pipeline(built)


def test_v3_keep_matrix_reused_build_pin_stays_local_to_one_instance() -> None:
    stage1 = astichi.build()
    stage1.add.Unit(_piece("value = 1\n"))
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pinned(built.with_keep_names(["value"]))
    stage2.add.Plain(built)
    materialized = stage2.build().materialize()
    source = materialized.emit(provenance=False)

    assert source.count("value = 1") == 1
    assert "value__astichi_scoped_" in source


@pytest.mark.parametrize(
    ("root_source", "insert_source", "expected_fragment"),
    [
        (
            "result = astichi_hole(value)\n",
            "astichi_insert(value, 42)\n",
            "result = 42",
        ),
        (
            "result = func(*astichi_hole(args))\n",
            "astichi_insert(args, first_arg)\nastichi_insert(args, second_arg, order=10)\n",
            "result = func(first_arg, second_arg)",
        ),
        (
            "result = func(**astichi_hole(kwargs))\n",
            "astichi_insert(kwargs, {first: one})\nastichi_insert(kwargs, {second: two}, order=20)\n",
            "result = func(first=one, second=two)",
        ),
    ],
)
def test_v3_expression_variadic_matrix_stage_built_sources(
    root_source: str,
    insert_source: str,
    expected_fragment: str,
) -> None:
    stage1 = astichi.build()
    stage1.add.Impl(_piece(insert_source))
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Root(_piece(root_source))
    stage2.add.Impl(built)

    target_name = "value"
    if "args" in root_source:
        target_name = "args"
    if "kwargs" in root_source:
        target_name = "kwargs"

    getattr(stage2.Root, target_name).add.Impl(order=0)

    source = stage2.build().materialize().emit(provenance=False)
    assert expected_fragment in source
    assert "astichi_hole" not in source
    assert "astichi_insert" not in source
