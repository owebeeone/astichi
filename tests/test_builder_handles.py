from __future__ import annotations

import pytest

import astichi
from astichi.builder import (
    AddProxy,
    AddToTargetProxy,
    AdditiveEdge,
    BuilderHandle,
    BuilderGraph,
    InstanceHandle,
    TargetHandle,
    TargetRef,
)
from astichi.builder.graph import AssignBinding


def test_build_returns_builder_handle_with_empty_graph() -> None:
    builder = astichi.build()

    assert isinstance(builder, BuilderHandle)
    assert isinstance(builder.add, AddProxy)
    assert builder.graph.instances == ()
    assert builder.graph.edges == ()


def test_builder_add_name_registers_instance_and_returns_instance_handle() -> None:
    builder = astichi.build()
    comp = astichi.compile("value = 1\n")

    instance = builder.add.A(comp)

    assert isinstance(instance, InstanceHandle)
    assert instance.root_instance == "A"
    assert [record.name for record in builder.graph.instances] == ["A"]


def test_builder_root_instance_lookup_returns_instance_handle() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("value = 1\n"))

    instance = builder.A

    assert isinstance(instance, InstanceHandle)
    assert instance == InstanceHandle(graph=builder.graph, root_instance="A")


def test_builder_unknown_root_instance_fails_immediately() -> None:
    builder = astichi.build()

    with pytest.raises(AttributeError, match="unknown builder instance: A"):
        _ = builder.A


def test_instance_handle_attribute_and_indexing_create_target_handles() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("value = 1\n"))

    target = builder.A.first
    indexed = target[0, 1]

    assert isinstance(target, TargetHandle)
    assert target.target == TargetRef(root_instance="A", target_name="first")
    assert isinstance(indexed, TargetHandle)
    assert indexed.target == TargetRef(
        root_instance="A",
        target_name="first",
        path=(0, 1),
    )


def test_target_handle_indexing_requires_integer_path_items() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("value = 1\n"))

    with pytest.raises(TypeError, match="target path indexes must be integers"):
        _ = builder.A.first["bad"]


def test_target_handle_exposes_fluent_add_proxy() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(slot)\n"))
    builder.add.B(astichi.compile("value = 1\n"))

    edge = builder.A.slot.add.B(order=10)

    assert isinstance(builder.A.slot.add, AddToTargetProxy)
    assert edge == AdditiveEdge(
        target=TargetRef(root_instance="A", target_name="slot"),
        source_instance="B",
        order=10,
    )
    assert builder.graph.edges == (edge,)


def test_fluent_and_raw_builder_operations_produce_equivalent_graph_state() -> None:
    root = astichi.compile("astichi_hole(slot)\n")
    child = astichi.compile("value = 1\n")

    fluent = astichi.build()
    fluent.add.A(root)
    fluent.add.B(child)
    fluent.A.slot.add.B(order=10)

    raw = BuilderGraph()
    raw.add_instance("A", root)
    raw.add_instance("B", child)
    raw.add_additive_edge(
        target=TargetRef(root_instance="A", target_name="slot"),
        source_instance="B",
        order=10,
    )

    assert fluent.graph.instances == raw.instances
    assert fluent.graph.edges == raw.edges


def test_builder_add_arg_names_resolves_slot_before_registration() -> None:
    # Issue 005 §6 / 5d: `builder.add.Step(piece, arg_names=...)`
    # applies `.bind_identifier` to the piece before registering it,
    # so build + materialize succeed without a second bind call.
    piece = astichi.compile(
        """
def step__astichi_arg__():
    return 1
"""
    )

    builder = astichi.build()
    builder.add.A(piece, arg_names={"step": "run"})

    instance = builder.graph.instances[0].composable
    assert dict(instance.arg_bindings) == {"step": "run"}

    merged = builder.build()
    materialized = merged.materialize()

    import ast as _ast

    rendered = _ast.unparse(materialized.tree)
    assert "__astichi_arg__" not in rendered
    assert "def run()" in rendered


def test_builder_add_keep_names_pins_identifier_through_merge() -> None:
    # Issue 005 §4 / 5d: `keep_names=` on builder `add` attaches to the
    # piece so the merged composable inherits the pin via the
    # per-instance union.
    piece = astichi.compile("value = _sentinel\n")

    builder = astichi.build()
    builder.add.A(piece, keep_names=["_sentinel"])

    assert "_sentinel" in builder.graph.instances[0].composable.keep_names

    merged = builder.build()
    assert "_sentinel" in merged.keep_names


def test_builder_add_arg_names_unknown_slot_fails_at_registration() -> None:
    piece = astichi.compile("value = 1\n")
    builder = astichi.build()
    with pytest.raises(
        ValueError,
        match=r"materialize: no __astichi_arg__ / astichi_import / astichi_pass slot named `missing`",
    ):
        builder.add.A(piece, arg_names={"missing": "x"})


def test_fluent_equal_order_keeps_insertion_order() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(slot)\n"))
    builder.add.B(astichi.compile("value = 1\n"))
    builder.add.C(astichi.compile("value = 2\n"))

    first = builder.A.slot.add.B(order=10)
    second = builder.A.slot.add.C(order=10)

    assert builder.graph.edges == (first, second)
    assert builder.graph.edges[0].source_instance == "B"
    assert builder.graph.edges[1].source_instance == "C"


def test_descendant_target_handles_accumulate_ref_path_across_build_stages() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile("astichi_hole(slot)\n"))
    stage1.Root.body.add.Inner()
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pipeline(built)

    target = stage2.Pipeline.Root.Inner.slot

    assert target == TargetHandle(
        graph=stage2.graph,
        target=TargetRef(
            root_instance="Pipeline",
            target_name="slot",
            ref_path=("Root", "Inner"),
        ),
    )


def test_descendant_target_handle_rejects_unknown_registered_path() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pipeline(built)

    with pytest.raises(
        ValueError,
        match=r"build: unknown descendant path `Pipeline\.Missing`",
    ):
        _ = stage2.Pipeline.Missing.body


def test_deep_target_add_rejects_unknown_leaf_in_registered_shell() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile("astichi_hole(slot)\n"))
    stage1.Root.body.add.Inner()
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pipeline(built)
    stage2.add.Step(astichi.compile("value = 1\n"))

    with pytest.raises(
        ValueError,
        match=r"build: unknown target site `Pipeline\.Root\.Inner\.missing`",
    ):
        stage2.Pipeline.Root.Inner.missing.add.Step()


def test_builder_add_rejects_duplicate_descendant_refs_in_reused_build() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile("value = 1\n"))
    stage1.Root.body.add.Inner(order=0)
    stage1.Root.body.add.Inner(order=1)
    built = stage1.build()

    stage2 = astichi.build()
    with pytest.raises(
        ValueError, match=r"build: instance .* ambiguous descendant ref"
    ):
        stage2.add.Pipeline(built)


def test_assign_descendant_target_records_full_ref_path() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile("total = 10\n"))
    stage1.Root.body.add.Inner()
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pipeline(built)
    stage2.add.Step(astichi.compile("astichi_import(total)\nvalue = total + 1\n"))

    stage2.assign.Step.total.to().Pipeline.Root.Inner.total

    assert stage2.graph.assigns == (
        AssignBinding(
            source_instance="Step",
            inner_name="total",
            target_instance="Pipeline",
            outer_name="total",
            target_ref_path=("Root", "Inner"),
        ),
    )


def test_assign_descendant_target_rejects_unknown_registered_path_cleanly() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pipeline(built)
    stage2.add.Step(astichi.compile("astichi_import(total)\nvalue = total + 1\n"))

    with pytest.raises(
        ValueError,
        match=(
            r"no readable supplier named `Missing` at `Pipeline\.Missing`"
        ),
    ):
        stage2.assign.Step.total.to().Pipeline.Missing.total

    assert stage2.graph.assigns == ()
