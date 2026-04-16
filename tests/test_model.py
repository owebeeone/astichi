from __future__ import annotations

import pytest

import astichi
from astichi.asttools import BLOCK, SCALAR_EXPR
from astichi.model import BasicComposable, DemandPort, IDENTIFIER, SupplyPort, validate_port_pair


def test_compile_returns_model_backed_composable_with_ports() -> None:
    compiled = astichi.compile(
        """
astichi_hole(body)
value = missing_name
astichi_export(result)


class class_name__astichi__:
    pass
"""
    )

    assert isinstance(compiled, astichi.Composable)
    assert isinstance(compiled, BasicComposable)
    assert [port.name for port in compiled.demand_ports] == ["body", "missing_name"]
    assert [port.name for port in compiled.supply_ports] == ["class_name", "result"]
    assert compiled.demand_ports[0].shape is BLOCK
    assert compiled.demand_ports[1].shape is SCALAR_EXPR
    assert compiled.supply_ports[0].shape is IDENTIFIER
    assert compiled.classification is not None


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


def test_compile_rejects_incompatible_supply_port_declarations() -> None:
    with pytest.raises(
        ValueError,
        match="incompatible supply-port declarations for result",
    ):
        astichi.compile(
            """
astichi_export(result)


def result__astichi__():
    return 1
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

    with pytest.raises(ValueError, match="incompatible port shape"):
        validate_port_pair(
            demand,
            SupplyPort(
                name="value_slot",
                shape=IDENTIFIER,
                placement="expr",
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
