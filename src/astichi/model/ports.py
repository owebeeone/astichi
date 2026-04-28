"""Demand and supply port structures for Astichi V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import TYPE_CHECKING

from astichi.asttools import BLOCK, IDENTIFIER, PARAMETER, SCALAR_EXPR, MarkerShape
from astichi.lowering import RecognizedMarker
from astichi.model.semantics import (
    ARG_IDENTIFIER_ORIGIN,
    BIND_EXTERNAL_ORIGIN,
    BLOCK_PLACEMENT,
    CALL_ARGUMENT_PLACEMENT,
    CONST_MUTABILITY,
    EXPRESSION_PLACEMENT,
    EXPORT_ORIGIN,
    HOLE_ORIGIN,
    IMPLIED_DEMAND_ORIGIN,
    IDENTIFIER_PLACEMENT,
    IMPORT_ORIGIN,
    INSERT_ORIGIN,
    PARAMETER_HOLE_ORIGIN,
    PARAMETER_PAYLOAD_ORIGIN,
    PASS_ORIGIN,
    SIGNATURE_PARAMETER_PLACEMENT,
    Compatibility,
    PortMutability,
    PortOrigin,
    PortOrigins,
    PortPlacement,
    normalize_port_mutability,
    normalize_port_placement,
    placement_for_shape,
)

if TYPE_CHECKING:
    from astichi.hygiene import NameClassification

# Re-exported so external consumers (tests, docs) can spell the
# IDENTIFIER shape as `astichi.model.ports.IDENTIFIER`. The canonical
# definition lives in `astichi.asttools.shapes`.
__all__ = (
    "BLOCK",
    "BLOCK_PLACEMENT",
    "CALL_ARGUMENT_PLACEMENT",
    "EXPRESSION_PLACEMENT",
    "IDENTIFIER",
    "IDENTIFIER_PLACEMENT",
    "PARAMETER",
    "SCALAR_EXPR",
    "SIGNATURE_PARAMETER_PLACEMENT",
    "ARG_IDENTIFIER_ORIGIN",
    "BIND_EXTERNAL_ORIGIN",
    "CONST_MUTABILITY",
    "DemandPort",
    "EXPORT_ORIGIN",
    "HOLE_ORIGIN",
    "IMPORT_ORIGIN",
    "INSERT_ORIGIN",
    "PARAMETER_HOLE_ORIGIN",
    "PARAMETER_PAYLOAD_ORIGIN",
    "PASS_ORIGIN",
    "PortMutability",
    "PortOrigin",
    "PortOrigins",
    "PortPlacement",
    "SupplyPort",
    "extract_demand_ports",
    "extract_supply_ports",
    "validate_port_pair",
)


@dataclass(frozen=True)
class DemandPort:
    """A demand-side port on a composable."""

    name: str
    shape: MarkerShape
    placement: PortPlacement
    mutability: PortMutability
    origins: PortOrigins = field(default_factory=lambda: PortOrigins(frozenset()))

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "placement", normalize_port_placement(self.placement)
        )
        object.__setattr__(
            self, "mutability", normalize_port_mutability(self.mutability)
        )

    def accepts_supply(self, supply: "SupplyPort") -> Compatibility:
        compatibility = self.placement.accepts_supply(self, supply)
        if not compatibility.is_accepted():
            return compatibility
        if (
            not self.placement.is_expression_family()
            and self.shape is not supply.shape
        ):
            return _shape_rejection(self.name, self.shape, supply.shape)
        return self.mutability.accepts_supply_mutability(supply.mutability)

    def is_external_bind_demand(self) -> bool:
        return self.origins.is_external_bind_demand()

    def is_identifier_demand(self) -> bool:
        return self.origins.is_identifier_demand()

    def is_additive_hole_demand(self) -> bool:
        return self.origins.is_additive_hole_demand()

    def is_parameter_hole_demand(self) -> bool:
        return self.origins.is_parameter_hole_demand()

    def is_signature_parameter_demand(self) -> bool:
        return self.placement.is_signature_parameter_family()

    def is_expression_family_demand(self) -> bool:
        return self.placement.is_expression_family()

    @property
    def sources(self) -> frozenset[str]:
        """Compatibility diagnostic view of origin names."""
        return self.origins.names


@dataclass(frozen=True)
class SupplyPort:
    """A supply-side port on a composable."""

    name: str
    shape: MarkerShape
    placement: PortPlacement
    mutability: PortMutability
    origins: PortOrigins = field(default_factory=lambda: PortOrigins(frozenset()))

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "placement", normalize_port_placement(self.placement)
        )
        object.__setattr__(
            self, "mutability", normalize_port_mutability(self.mutability)
        )

    def is_expression_family_supply(self) -> bool:
        return self.placement.is_expression_family()

    def is_signature_parameter_supply(self) -> bool:
        return self.placement.is_signature_parameter_family()

    @property
    def sources(self) -> frozenset[str]:
        """Compatibility diagnostic view of origin names."""
        return self.origins.names


def extract_demand_ports(
    markers: tuple[RecognizedMarker, ...],
    classification: NameClassification,
) -> tuple[DemandPort, ...]:
    """Extract demand ports from lowering and hygiene artifacts.

    Per-marker knowledge lives on the marker spec itself: each
    `MarkerSpec` returns a `PortTemplate` (or `None`) from
    `demand_template(marker)`. This function is pure glue — it pairs
    those templates with the marker's `name_id`, derives `placement`
    from `shape`, and merges duplicates.
    """
    ports: list[DemandPort] = []
    for marker in markers:
        if marker.name_id is None:
            continue
        template = marker.spec.demand_template(marker)
        if template is None:
            continue
        ports.append(
            DemandPort(
                name=marker.name_id,
                shape=template.shape,
                placement=placement_for_shape(template.shape),
                mutability=template.mutability,
                origins=PortOrigins.of(template.origin),
            )
        )
    for implied in classification.implied_demands:
        ports.append(
            DemandPort(
                name=implied.name,
                shape=SCALAR_EXPR,
                placement=placement_for_shape(SCALAR_EXPR),
                mutability=CONST_MUTABILITY,
                origins=PortOrigins.of(IMPLIED_DEMAND_ORIGIN),
            )
        )
    return _merge_demand_ports(ports)


def extract_supply_ports(
    markers: tuple[RecognizedMarker, ...],
) -> tuple[SupplyPort, ...]:
    """Extract supply ports from lowering artifacts.

    Mirrors `extract_demand_ports`: the marker spec provides the
    `PortTemplate` via `supply_template(marker)`; this function is
    purely the glue that materialises it into a `SupplyPort`.
    """
    ports: list[SupplyPort] = []
    for marker in markers:
        if marker.name_id is None:
            continue
        template = marker.spec.supply_template(marker)
        if template is None:
            continue
        ports.append(
            SupplyPort(
                name=marker.name_id,
                shape=template.shape,
                placement=placement_for_shape(template.shape),
                mutability=template.mutability,
                origins=PortOrigins.of(template.origin),
            )
        )
    return _merge_supply_ports(ports)


def validate_port_pair(demand: DemandPort, supply: SupplyPort) -> None:
    """Validate that a supply port can satisfy a demand port."""
    compatibility = demand.accepts_supply(supply)
    if not compatibility.is_accepted():
        raise ValueError(compatibility.error_message())


def _merge_demand_ports(ports: list[DemandPort]) -> tuple[DemandPort, ...]:
    merged: list[DemandPort] = []
    for name, group_iter in groupby(sorted(ports, key=lambda port: port.name), key=lambda port: port.name):
        group = list(group_iter)
        exemplar = group[0]
        for port in group[1:]:
            if (
                port.shape is not exemplar.shape
                or port.placement is not exemplar.placement
                or port.mutability is not exemplar.mutability
            ):
                raise ValueError(f"incompatible demand-port declarations for {name}")
        merged.append(
            DemandPort(
                name=name,
                shape=exemplar.shape,
                placement=exemplar.placement,
                mutability=exemplar.mutability,
                origins=PortOrigins(
                    frozenset().union(*(port.origins.items for port in group))
                ),
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
                or port.placement is not exemplar.placement
                or port.mutability is not exemplar.mutability
            ):
                raise ValueError(f"incompatible supply-port declarations for {name}")
        merged.append(
            SupplyPort(
                name=name,
                shape=exemplar.shape,
                placement=exemplar.placement,
                mutability=exemplar.mutability,
                origins=PortOrigins(
                    frozenset().union(*(port.origins.items for port in group))
                ),
            )
        )
    return tuple(merged)


def _shape_rejection(
    name: str, demand_shape: MarkerShape, supply_shape: MarkerShape
) -> Compatibility:
    from astichi.model.semantics import RejectedCompatibility

    return RejectedCompatibility(
        f"incompatible port shape for {name}: "
        f"{demand_shape.name} != {supply_shape.name}"
    )
