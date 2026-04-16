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
