from __future__ import annotations

import ast

import pytest

import astichi
from astichi.model import BasicComposable


def test_build_simple_block_hole_replacement() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(body)\n"))
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.body.add.B()

    result = builder.build()

    assert isinstance(result, BasicComposable)
    rendered = ast.unparse(result.tree)
    assert "value = 1" in rendered
    assert "astichi_hole" not in rendered


def test_build_preserves_surrounding_code() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("x = 1\nastichi_hole(body)\ny = 2\n"))
    builder.add.B(astichi.compile("z = 3\n"))
    builder.A.body.add.B()

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "x = 1" in rendered
    assert "z = 3" in rendered
    assert "y = 2" in rendered
    assert "astichi_hole" not in rendered


def test_build_multiple_sources_ordered() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(body)\n"))
    builder.add.B(astichi.compile("x = 1\n"))
    builder.add.C(astichi.compile("y = 2\n"))
    builder.A.body.add.C(order=5)
    builder.A.body.add.B(order=10)

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert rendered.index("y = 2") < rendered.index("x = 1")


def test_build_equal_order_preserves_insertion_order() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(body)\n"))
    builder.add.B(astichi.compile("x = 1\n"))
    builder.add.C(astichi.compile("y = 2\n"))
    builder.A.body.add.B(order=0)
    builder.A.body.add.C(order=0)

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert rendered.index("x = 1") < rendered.index("y = 2")


def test_build_unresolved_holes_remain() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile("astichi_hole(filled)\nastichi_hole(unfilled)\n")
    )
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.filled.add.B()

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "value = 1" in rendered
    assert "astichi_hole(unfilled)" in rendered
    assert [p.name for p in result.demand_ports] == ["unfilled"]


def test_build_chain_resolution() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(outer)\n"))
    builder.add.B(astichi.compile("x = 1\nastichi_hole(inner)\n"))
    builder.add.C(astichi.compile("y = 2\n"))
    builder.A.outer.add.B()
    builder.B.inner.add.C()

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "x = 1" in rendered
    assert "y = 2" in rendered
    assert "astichi_hole" not in rendered


def test_build_no_edges_concatenates_bodies() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("x = 1\n"))
    builder.add.B(astichi.compile("y = 2\n"))

    result = builder.build()

    rendered = ast.unparse(result.tree)
    assert "x = 1" in rendered
    assert "y = 2" in rendered


def test_build_updates_demand_and_supply_ports() -> None:
    builder = astichi.build()
    builder.add.A(astichi.compile("astichi_hole(slot)\nastichi_export(out)\n"))
    builder.add.B(astichi.compile("value = 1\n"))
    builder.A.slot.add.B()

    result = builder.build()

    demand_names = [p.name for p in result.demand_ports]
    supply_names = [p.name for p in result.supply_ports]
    assert "slot" not in demand_names
    assert "out" in supply_names


def test_build_empty_graph_raises() -> None:
    builder = astichi.build()

    with pytest.raises(ValueError, match="cannot build from empty graph"):
        builder.build()
