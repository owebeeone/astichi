"""Demand and supply port structures for Astichi V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import TYPE_CHECKING

from astichi.asttools import BLOCK, SCALAR_EXPR, MarkerShape
from astichi.lowering import RecognizedMarker

if TYPE_CHECKING:
    from astichi.hygiene import NameClassification


class _IdentifierShape(MarkerShape):
    def __init__(self) -> None:
        super().__init__("identifier")


IDENTIFIER = _IdentifierShape()


@dataclass(frozen=True)
class DemandPort:
    """A demand-side port on a composable."""

    name: str
    shape: MarkerShape
    placement: str
    mutability: str
    sources: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SupplyPort:
    """A supply-side port on a composable."""

    name: str
    shape: MarkerShape
    placement: str
    mutability: str
    sources: frozenset[str] = field(default_factory=frozenset)


def extract_demand_ports(
    markers: tuple[RecognizedMarker, ...],
    classification: NameClassification,
) -> tuple[DemandPort, ...]:
    """Extract demand ports from lowering and hygiene artifacts."""
    ports: list[DemandPort] = []
    for marker in markers:
        if marker.source_name != "astichi_hole" or marker.name_id is None:
            continue
        assert marker.shape is not None
        ports.append(
            DemandPort(
                name=marker.name_id,
                shape=marker.shape,
                placement=_placement_for_shape(marker.shape),
                mutability="const",
                sources=frozenset({"hole"}),
            )
        )
    for implied in classification.implied_demands:
        ports.append(
            DemandPort(
                name=implied.name,
                shape=SCALAR_EXPR,
                placement="expr",
                mutability="const",
                sources=frozenset({"implied"}),
            )
        )
    return _merge_demand_ports(ports)


def extract_supply_ports(
    markers: tuple[RecognizedMarker, ...],
) -> tuple[SupplyPort, ...]:
    """Extract supply ports from lowering artifacts."""
    ports: list[SupplyPort] = []
    for marker in markers:
        if marker.name_id is None:
            continue
        if marker.source_name == "astichi_export":
            ports.append(
                SupplyPort(
                    name=marker.name_id,
                    shape=SCALAR_EXPR,
                    placement="expr",
                    mutability="const",
                    sources=frozenset({"export"}),
                )
            )
            continue
        if marker.source_name == "astichi_definitional_name":
            ports.append(
                SupplyPort(
                    name=marker.name_id,
                    shape=IDENTIFIER,
                    placement="identifier",
                    mutability="const",
                    sources=frozenset({"definitional"}),
                )
            )
    return _merge_supply_ports(ports)


def validate_port_pair(demand: DemandPort, supply: SupplyPort) -> None:
    """Validate that a supply port can satisfy a demand port."""
    if demand.placement != supply.placement:
        raise ValueError(
            f"incompatible port placement for {demand.name}: "
            f"{demand.placement} != {supply.placement}"
        )
    if demand.shape is not supply.shape:
        raise ValueError(
            f"incompatible port shape for {demand.name}: "
            f"{demand.shape.name} != {supply.shape.name}"
        )
    if demand.mutability != supply.mutability:
        raise ValueError(
            f"incompatible port mutability for {demand.name}: "
            f"{demand.mutability} != {supply.mutability}"
        )


def _merge_demand_ports(ports: list[DemandPort]) -> tuple[DemandPort, ...]:
    merged: list[DemandPort] = []
    for name, group_iter in groupby(sorted(ports, key=lambda port: port.name), key=lambda port: port.name):
        group = list(group_iter)
        exemplar = group[0]
        for port in group[1:]:
            if (
                port.shape is not exemplar.shape
                or port.placement != exemplar.placement
                or port.mutability != exemplar.mutability
            ):
                raise ValueError(f"incompatible demand-port declarations for {name}")
        merged.append(
            DemandPort(
                name=name,
                shape=exemplar.shape,
                placement=exemplar.placement,
                mutability=exemplar.mutability,
                sources=frozenset().union(*(port.sources for port in group)),
            )
        )
    return tuple(merged)


def _merge_supply_ports(ports: list[SupplyPort]) -> tuple[SupplyPort, ...]:
    merged: list[SupplyPort] = []
    for name, group_iter in groupby(sorted(ports, key=lambda port: port.name), key=lambda port: port.name):
        group = list(group_iter)
        exemplar = group[0]
        for port in group[1:]:
            if (
                port.shape is not exemplar.shape
                or port.placement != exemplar.placement
                or port.mutability != exemplar.mutability
            ):
                raise ValueError(f"incompatible supply-port declarations for {name}")
        merged.append(
            SupplyPort(
                name=name,
                shape=exemplar.shape,
                placement=exemplar.placement,
                mutability=exemplar.mutability,
                sources=frozenset().union(*(port.sources for port in group)),
            )
        )
    return tuple(merged)


def _placement_for_shape(shape: MarkerShape) -> str:
    if shape is BLOCK:
        return "block"
    if shape is IDENTIFIER:
        return "identifier"
    return "expr"
