from __future__ import annotations

import pytest

import astichi
from astichi.builder import AddProxy, BuilderHandle, InstanceHandle, TargetHandle, TargetRef


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
