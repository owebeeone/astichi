"""ComposableDescription adapter for inventory records."""

from __future__ import annotations

from collections.abc import Iterable

from astichi.model.descriptors import (
    ComposableDescription,
    ComposableHole,
    ExternalBindDescriptor,
    HoleDescriptor,
    IdentifierDemandDescriptor,
    IdentifierSupplyDescriptor,
    PortDescriptor,
    ProductionDescriptor,
    TargetAddress,
    add_policy_for_demand,
    block_production,
    expression_ast_production,
    funcargs_production,
)
from astichi.model.inventory import (
    BlockProductionInventoryPayload,
    ExpressionProductionInventoryPayload,
    FuncargsProductionInventoryPayload,
    Inventory,
    InventoryRecord,
    PortInventoryPayload,
)
from astichi.model.ports import DemandPort, SupplyPort


def describe_inventory(inventory: Inventory) -> ComposableDescription:
    """Return the public descriptor view for ``inventory``."""
    return ComposableDescription(
        holes=_describe_holes(inventory),
        demand_ports=_describe_demand_ports(inventory),
        supply_ports=_describe_supply_ports(inventory),
        external_binds=_describe_external_binds(inventory),
        identifier_demands=_describe_identifier_demands(inventory),
        identifier_supplies=_describe_identifier_supplies(inventory),
        productions=_describe_productions(inventory),
    )


def _records_by_ref_and_name(
    records: Iterable[InventoryRecord],
) -> tuple[InventoryRecord, ...]:
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.build_path.parts,
                record.name.logical_name(),
                record.record_id,
            ),
        )
    )


def _port_payload(record: InventoryRecord) -> PortInventoryPayload | None:
    if isinstance(record.payload, PortInventoryPayload):
        return record.payload
    return None


def _describe_demand_ports(inventory: Inventory) -> tuple[PortDescriptor, ...]:
    descriptors: list[PortDescriptor] = []
    seen: set[PortDescriptor] = set()
    for record in _records_by_ref_and_name(inventory.records.values()):
        payload = _port_payload(record)
        if payload is None or not isinstance(payload.port, DemandPort):
            continue
        descriptor = PortDescriptor.from_demand(payload.port)
        if descriptor in seen:
            continue
        seen.add(descriptor)
        descriptors.append(descriptor)
    return tuple(sorted(descriptors, key=lambda descriptor: descriptor.name))


def _describe_supply_ports(inventory: Inventory) -> tuple[PortDescriptor, ...]:
    descriptors: list[PortDescriptor] = []
    seen: set[PortDescriptor] = set()
    for record in _records_by_ref_and_name(inventory.records.values()):
        payload = _port_payload(record)
        if payload is None or not isinstance(payload.port, SupplyPort):
            continue
        descriptor = PortDescriptor.from_supply(payload.port)
        if descriptor in seen:
            continue
        seen.add(descriptor)
        descriptors.append(descriptor)
    return tuple(sorted(descriptors, key=lambda descriptor: descriptor.name))


def _record_ref_path(record: InventoryRecord) -> tuple[str, ...]:
    return record.build_path.parts


def _describe_holes(inventory: Inventory) -> tuple[ComposableHole, ...]:
    holes: list[ComposableHole] = []
    records = _records_by_ref_and_name(
        inventory.records_for_ids(
            tuple(
                record_id
                for ids in inventory.hole_map.values()
                for record_id in ids
            )
        )
    )
    for record in records:
        payload = _port_payload(record)
        if payload is None or not isinstance(payload.port, DemandPort):
            continue
        port = payload.port
        if not (port.is_additive_hole_demand() or port.is_parameter_hole_demand()):
            continue
        name = record.name.logical_name()
        port_descriptor = PortDescriptor.from_demand(port)
        hole_descriptor = HoleDescriptor(port=port_descriptor)
        holes.append(
            ComposableHole(
                name=name,
                descriptor=hole_descriptor,
                address=TargetAddress(
                    root_instance=None,
                    ref_path=_record_ref_path(record),
                    target_name=name,
                ),
                port=port_descriptor,
                add_policy=add_policy_for_demand(port),
            )
        )
    return tuple(holes)


def _describe_external_binds(
    inventory: Inventory,
) -> tuple[ExternalBindDescriptor, ...]:
    descriptors: list[ExternalBindDescriptor] = []
    records = _records_by_ref_and_name(inventory.records.values())
    for record in records:
        if record.kind != "external.bind":
            continue
        payload = _port_payload(record)
        if payload is None or not isinstance(payload.port, DemandPort):
            continue
        descriptors.append(
            ExternalBindDescriptor(
                name=record.name.logical_name(),
                port=PortDescriptor.from_demand(payload.port),
            )
        )
    return tuple(descriptors)


def _describe_identifier_demands(
    inventory: Inventory,
) -> tuple[IdentifierDemandDescriptor, ...]:
    descriptors: list[IdentifierDemandDescriptor] = []
    records = _records_by_ref_and_name(
        inventory.records_for_ids(
            tuple(
                record_id
                for ids in inventory.identifier_map.values()
                for record_id in ids
            )
        )
    )
    for record in records:
        if record.kind != "identifier.demand":
            continue
        payload = _port_payload(record)
        if payload is None or not isinstance(payload.port, DemandPort):
            continue
        descriptors.append(
            IdentifierDemandDescriptor(
                name=record.name.logical_name(),
                port=PortDescriptor.from_demand(payload.port),
                ref_path=_record_ref_path(record),
            )
        )
    return tuple(descriptors)


def _describe_identifier_supplies(
    inventory: Inventory,
) -> tuple[IdentifierSupplyDescriptor, ...]:
    descriptors: list[IdentifierSupplyDescriptor] = []
    records = _records_by_ref_and_name(
        inventory.records_for_ids(
            tuple(
                record_id
                for ids in inventory.identifier_map.values()
                for record_id in ids
            )
        )
    )
    for record in records:
        if record.kind != "identifier.supply":
            continue
        payload = _port_payload(record)
        if payload is None or not isinstance(payload.port, SupplyPort):
            continue
        descriptors.append(
            IdentifierSupplyDescriptor(
                name=record.name.logical_name(),
                port=PortDescriptor.from_supply(payload.port),
                ref_path=_record_ref_path(record),
            )
        )
    return tuple(descriptors)


def _describe_productions(inventory: Inventory) -> tuple[ProductionDescriptor, ...]:
    productions: list[ProductionDescriptor] = []
    record_ids = tuple(
        record_id
        for ids in inventory.production_map.values()
        for record_id in ids
    )
    records = _production_records_by_order(inventory.records_for_ids(record_ids))
    for record in records:
        if record.kind == "production.supply":
            payload = _port_payload(record)
            if payload is None or not isinstance(payload.port, SupplyPort):
                continue
            productions.append(
                ProductionDescriptor(
                    name=record.name.logical_name(),
                    port=PortDescriptor.from_supply(payload.port),
                )
            )
            continue
        if isinstance(record.payload, FuncargsProductionInventoryPayload):
            productions.append(
                funcargs_production(
                    record.payload.payload,
                    name=record.name.logical_name(),
                )
            )
            continue
        if isinstance(record.payload, ExpressionProductionInventoryPayload):
            productions.append(
                expression_ast_production(
                    record.payload.expression,
                    name=record.name.logical_name(),
                )
            )
            continue
        if isinstance(record.payload, BlockProductionInventoryPayload):
            productions.append(block_production(record.name.logical_name()))
    return tuple(productions)


def _production_records_by_order(
    records: Iterable[InventoryRecord],
) -> tuple[InventoryRecord, ...]:
    return tuple(
        sorted(
            records,
            key=lambda record: (
                _production_kind_order(record.kind),
                record.name.logical_name(),
                record.record_id,
            ),
        )
    )


def _production_kind_order(kind: str) -> int:
    if kind == "production.supply":
        return 0
    if kind == "production.funcargs":
        return 1
    if kind == "production.expression":
        return 2
    if kind == "production.block":
        return 3
    return 4
