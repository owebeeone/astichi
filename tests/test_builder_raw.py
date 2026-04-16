from __future__ import annotations

import pytest

import astichi
from astichi.builder import AdditiveEdge, BuilderGraph, InstanceRecord, TargetRef


def test_build_returns_raw_builder_graph() -> None:
    builder = astichi.build()

    assert isinstance(builder, BuilderGraph)
    assert builder.instances == ()
    assert builder.edges == ()


def test_raw_builder_graph_registers_named_instances() -> None:
    builder = astichi.build()
    left = astichi.compile("value = 1\n")
    right = astichi.compile("astichi_hole(slot)\n")

    a = builder.add_instance("A", left)
    b = builder.add_instance("B", right)

    assert isinstance(a, InstanceRecord)
    assert isinstance(b, InstanceRecord)
    assert [record.name for record in builder.instances] == ["A", "B"]


def test_raw_builder_graph_rejects_invalid_or_duplicate_instance_names() -> None:
    builder = astichi.build()
    comp = astichi.compile("value = 1\n")

    with pytest.raises(ValueError, match="valid identifier"):
        builder.add_instance("not-valid-name", comp)

    builder.add_instance("A", comp)
    with pytest.raises(ValueError, match="duplicate instance name: A"):
        builder.add_instance("A", comp)


def test_raw_builder_graph_registers_additive_edges() -> None:
    builder = astichi.build()
    root = astichi.compile("astichi_hole(slot)\n")
    child = astichi.compile("value = 1\n")
    builder.add_instance("A", root)
    builder.add_instance("B", child)

    edge = builder.add_additive_edge(
        target=TargetRef(root_instance="A", target_name="slot", path=(0, 1)),
        source_instance="B",
        order=10,
    )

    assert isinstance(edge, AdditiveEdge)
    assert builder.edges == (
        AdditiveEdge(
            target=TargetRef(root_instance="A", target_name="slot", path=(0, 1)),
            source_instance="B",
            order=10,
        ),
    )


def test_raw_builder_graph_rejects_edges_with_unknown_instances() -> None:
    builder = astichi.build()
    builder.add_instance("A", astichi.compile("astichi_hole(slot)\n"))

    with pytest.raises(ValueError, match="unknown source instance: B"):
        builder.add_additive_edge(
            target=TargetRef(root_instance="A", target_name="slot"),
            source_instance="B",
        )

    builder.add_instance("B", astichi.compile("value = 1\n"))
    with pytest.raises(ValueError, match="unknown target root instance: C"):
        builder.add_additive_edge(
            target=TargetRef(root_instance="C", target_name="slot"),
            source_instance="B",
        )
