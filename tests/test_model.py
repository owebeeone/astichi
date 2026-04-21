from __future__ import annotations

import pytest

import astichi
from astichi.asttools import BLOCK, NAMED_VARIADIC, POSITIONAL_VARIADIC, SCALAR_EXPR
from astichi.model import BasicComposable, DemandPort, IDENTIFIER, SupplyPort, validate_port_pair


def test_compile_returns_model_backed_composable_with_ports() -> None:
    compiled = astichi.compile(
        """
astichi_hole(body)
value = missing_name
astichi_export(result)


class class_name__astichi_arg__:
    pass
"""
    )

    assert isinstance(compiled, astichi.Composable)
    assert isinstance(compiled, BasicComposable)
    # Issue 005 §2: `__astichi_arg__` sites expose IDENTIFIER-shape
    # demand ports; order is name-sorted by `_merge_demand_ports`.
    assert [port.name for port in compiled.demand_ports] == [
        "body",
        "class_name",
        "missing_name",
    ]
    assert [port.name for port in compiled.supply_ports] == ["result"]
    demand_by_name = {port.name: port for port in compiled.demand_ports}
    assert demand_by_name["body"].shape is BLOCK
    assert demand_by_name["missing_name"].shape is SCALAR_EXPR
    assert demand_by_name["class_name"].shape is IDENTIFIER
    assert demand_by_name["class_name"].sources == frozenset({"arg"})
    assert compiled.classification is not None


def test_bind_external_produces_demand_port() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(fields)
"""
    )

    assert [port.name for port in compiled.demand_ports] == ["fields"]
    demand = compiled.demand_ports[0]
    assert demand.shape is SCALAR_EXPR
    assert demand.placement == "expr"
    assert demand.mutability == "const"
    assert demand.sources == frozenset({"bind_external"})


def test_multiple_bind_external_markers_produce_multiple_demand_ports() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(fields)
astichi_bind_external(row_count)
"""
    )

    assert [port.name for port in compiled.demand_ports] == ["fields", "row_count"]
    assert all(port.sources == frozenset({"bind_external"}) for port in compiled.demand_ports)


def test_compile_rejects_incompatible_demand_port_declarations() -> None:
    with pytest.raises(
        ValueError,
        match="incompatible demand-port declarations for slot",
    ):
        astichi.compile(
            """
astichi_hole(slot)
value = astichi_hole(slot)
"""
        )


def test_compile_rejects_incompatible_demand_port_declarations_across_shapes() -> None:
    # Issue 005 retires the IDENTIFIER supply branch (previously backed by
    # `__astichi__` / `astichi_definitional_name`). The cross-shape
    # collision path is now demand-side: a scalar-expr bind-external slot
    # and an identifier-shape `__astichi_arg__` slot with the same name.
    with pytest.raises(
        ValueError,
        match="incompatible demand-port declarations for result",
    ):
        astichi.compile(
            """
astichi_bind_external(result)


class result__astichi_arg__:
    pass
"""
        )


def test_validate_port_pair_rejects_shape_placement_and_mutability_mismatch() -> None:
    demand = DemandPort(
        name="value_slot",
        shape=SCALAR_EXPR,
        placement="expr",
        mutability="const",
    )
    good_supply = SupplyPort(
        name="value_slot",
        shape=SCALAR_EXPR,
        placement="expr",
        mutability="const",
    )
    validate_port_pair(demand, good_supply)

    block_demand = DemandPort(
        name="block_slot",
        shape=BLOCK,
        placement="block",
        mutability="const",
    )
    with pytest.raises(ValueError, match="incompatible port shape"):
        validate_port_pair(
            block_demand,
            SupplyPort(
                name="block_slot",
                shape=SCALAR_EXPR,
                placement="block",
                mutability="const",
            ),
        )

    with pytest.raises(ValueError, match="incompatible port placement"):
        validate_port_pair(
            demand,
            SupplyPort(
                name="value_slot",
                shape=SCALAR_EXPR,
                placement="identifier",
                mutability="const",
            ),
        )

    with pytest.raises(ValueError, match="incompatible port mutability"):
        validate_port_pair(
            demand,
            SupplyPort(
                name="value_slot",
                shape=SCALAR_EXPR,
                placement="expr",
                mutability="mutable",
            ),
        )


def test_expression_insert_produces_supply_port() -> None:
    compiled = astichi.compile(
        """
value = astichi_insert(target_slot, 42)
""",
        source_kind="astichi-emitted",
    )

    supply = [p for p in compiled.supply_ports if p.name == "target_slot"]
    assert len(supply) == 1
    assert supply[0].shape is SCALAR_EXPR
    assert supply[0].placement == "expr"
    assert supply[0].mutability == "const"
    assert "insert" in supply[0].sources


def test_decorator_insert_does_not_produce_supply_port() -> None:
    compiled = astichi.compile(
        """
@astichi_insert(block_target)
def inject():
    return 1
""",
        source_kind="astichi-emitted",
    )

    supply = [p for p in compiled.supply_ports if p.name == "block_target"]
    assert len(supply) == 0


def test_expr_supply_matches_expr_demand_any_sub_shape() -> None:
    scalar_supply = SupplyPort(
        name="slot",
        shape=SCALAR_EXPR,
        placement="expr",
        mutability="const",
    )
    for demand_shape in (SCALAR_EXPR, POSITIONAL_VARIADIC, NAMED_VARIADIC):
        demand = DemandPort(
            name="slot",
            shape=demand_shape,
            placement="expr",
            mutability="const",
        )
        validate_port_pair(demand, scalar_supply)


def test_expr_supply_does_not_match_block_demand() -> None:
    demand = DemandPort(
        name="slot",
        shape=BLOCK,
        placement="block",
        mutability="const",
    )
    supply = SupplyPort(
        name="slot",
        shape=SCALAR_EXPR,
        placement="expr",
        mutability="const",
    )
    with pytest.raises(ValueError, match="incompatible port placement"):
        validate_port_pair(demand, supply)


def test_block_supply_does_not_match_expr_demand() -> None:
    demand = DemandPort(
        name="slot",
        shape=SCALAR_EXPR,
        placement="expr",
        mutability="const",
    )
    supply = SupplyPort(
        name="slot",
        shape=BLOCK,
        placement="block",
        mutability="const",
    )
    with pytest.raises(ValueError, match="incompatible port placement"):
        validate_port_pair(demand, supply)
