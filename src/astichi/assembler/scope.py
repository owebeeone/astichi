"""Inventory-driven assembly scope helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TypeAlias

from astichi.ast_provenance import astichi_source_file
from astichi.builder.graph import (
    format_indexed_instance_name,
    parse_indexed_instance_name,
)
from astichi.builder.handles import BuilderHandle, InstanceHandle
from astichi.model import (
    BasicComposable,
    BlockProductionInventoryPayload,
    ClassCodePathNode,
    CodePath,
    CodePathNode,
    ExpressionProductionInventoryPayload,
    FunctionCodePathNode,
    FuncargsProductionInventoryPayload,
    HoleDescriptor,
    Inventory,
    InventoryRecord,
    InventoryRecordId,
    MutableInventory,
    PortDescriptor,
    PortInventoryPayload,
    ProductionDescriptor,
    ResourcePath,
    SourceLocation,
    empty_inventory,
)
from astichi.model.composable import Composable
from astichi.model.descriptors import (
    block_production,
    elif_production,
    expression_ast_production,
    funcargs_production,
)
from astichi.model.ports import DemandPort, SupplyPort
from astichi.pathmatch import matches_path

ExternalValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | tuple["ExternalValue", ...]
    | list["ExternalValue"]
    | dict["ExternalValue", "ExternalValue"]
)


@dataclass(frozen=True)
class DemandSelector:
    """Selector for demand records in an inventory."""

    name: str | None = None
    build_match: tuple[str, ...] | None = None
    owner_match: tuple[str, ...] | None = None


class BindingResource(ABC):
    """Client-supplied resource that can satisfy one kind of Astichi demand."""

    @abstractmethod
    def find_candidates(
        self, inventory: Inventory, selector: DemandSelector
    ) -> tuple["BindingCandidate", ...]:
        """Return matching candidates for this resource."""

    def diagnostic_lines(self) -> tuple[str, ...]:
        """Return resource-side diagnostic lines for candidate reports."""
        return (f"resource: {type(self).__name__}",)


class BindingCandidate(ABC):
    """One possible way to apply a binding resource to an assembly scope."""

    @abstractmethod
    def diagnostic_lines(self) -> tuple[str, ...]:
        """Return diagnostic lines for this candidate."""


@dataclass(frozen=True)
class ComposableResource(BindingResource):
    """Composable resource that can satisfy compatible additive holes."""

    composable: Composable
    build_name: str
    build_index: int | tuple[int, ...] | None = None
    order: int = 0

    @property
    def instance_name(self) -> str:
        """Return the concrete builder instance name for this resource."""
        if self.build_index is None:
            return self.build_name
        indexes = (
            self.build_index
            if isinstance(self.build_index, tuple)
            else (self.build_index,)
        )
        return format_indexed_instance_name(self.build_name, indexes)

    def find_candidates(
        self, inventory: Inventory, selector: DemandSelector
    ) -> tuple[BindingCandidate, ...]:
        production_records = _production_records(self.composable)
        candidates: list[BindingCandidate] = []
        for target_record in _records_for_map(inventory, inventory.hole_map, selector):
            hole = _hole_descriptor(target_record)
            if hole is None:
                continue
            compatible = tuple(
                production
                for production in production_records
                if _production_satisfies(production, hole)
            )
            if not compatible:
                continue
            candidates.append(
                ComposableCandidate(
                    target_record=target_record,
                    resource=self,
                    compatible_productions=compatible,
                )
            )
        return tuple(candidates)

    def diagnostic_lines(self) -> tuple[str, ...]:
        lines = [f"resource: composable build_name={self.instance_name}"]
        for record in _production_records(self.composable):
            lines.append(f"  production: {_format_resource_record(record)}")
        return tuple(lines)


@dataclass(frozen=True)
class ExternalValueResource(BindingResource):
    """External value that can satisfy ``astichi_bind_external`` demands."""

    value: ExternalValue

    def find_candidates(
        self, inventory: Inventory, selector: DemandSelector
    ) -> tuple[BindingCandidate, ...]:
        return tuple(
            ExternalValueCandidate(demand_record=record, resource=self)
            for record in _records_for_map(inventory, inventory.port_map, selector)
            if record.kind == "external.bind"
        )

    def diagnostic_lines(self) -> tuple[str, ...]:
        return ("resource: external value",)


@dataclass(frozen=True)
class IdentifierNameResource(BindingResource):
    """Identifier spelling that can satisfy identifier-demand records."""

    identifier: str

    def find_candidates(
        self, inventory: Inventory, selector: DemandSelector
    ) -> tuple[BindingCandidate, ...]:
        return tuple(
            IdentifierNameCandidate(demand_record=record, resource=self)
            for record in _records_for_map(inventory, inventory.identifier_map, selector)
            if record.kind == "identifier.demand"
        )

    def diagnostic_lines(self) -> tuple[str, ...]:
        return (f"resource: identifier {self.identifier}",)


@dataclass(frozen=True)
class ComposableCandidate(BindingCandidate):
    """Candidate insertion of a composable into a compatible target hole."""

    target_record: InventoryRecord
    resource: ComposableResource
    compatible_productions: tuple[InventoryRecord, ...]

    def diagnostic_lines(self) -> tuple[str, ...]:
        return (
            f"demand: {_format_demand_record(self.target_record)}",
            *self.resource.diagnostic_lines(),
        )


@dataclass(frozen=True)
class ExternalValueCandidate(BindingCandidate):
    """Candidate external value binding."""

    demand_record: InventoryRecord
    resource: ExternalValueResource

    def diagnostic_lines(self) -> tuple[str, ...]:
        return (
            f"demand: {_format_demand_record(self.demand_record)}",
            *self.resource.diagnostic_lines(),
        )


@dataclass(frozen=True)
class IdentifierNameCandidate(BindingCandidate):
    """Candidate direct identifier-name binding."""

    demand_record: InventoryRecord
    resource: IdentifierNameResource

    def diagnostic_lines(self) -> tuple[str, ...]:
        return (
            f"demand: {_format_demand_record(self.demand_record)}",
            *self.resource.diagnostic_lines(),
        )


@dataclass
class AssemblyScope:
    """Builder wrapper that can apply inventory-selected binding candidates."""

    builder: BuilderHandle
    _inventory: Inventory = field(default_factory=empty_inventory, init=False)
    _owner_by_build_prefix: dict[tuple[str, ...], str] = field(
        default_factory=dict, init=False
    )
    _record_ids_by_build_prefix: dict[tuple[str, ...], frozenset[InventoryRecordId]] = (
        field(default_factory=dict, init=False)
    )
    _satisfied_record_ids: set[InventoryRecordId] = field(
        default_factory=set, init=False
    )

    def __post_init__(self) -> None:
        if self.builder.graph.instances:
            self._refresh_inventory_from_build()

    @property
    def inventory(self) -> Inventory:
        """Return the current built inventory view for this scope."""
        return self._inventory

    def add(self, name: str, composable: Composable) -> InstanceHandle:
        """Register a root composable in this scope."""
        handle = self.builder.add(name, composable)
        self._owner_by_build_prefix[(name,)] = name
        self._replace_occurrence_inventory((name,), composable)
        return handle

    def apply(self, candidate: BindingCandidate) -> None:
        """Apply one candidate to the underlying builder graph."""
        if isinstance(candidate, ComposableCandidate):
            self._apply_composable(candidate)
            return
        if isinstance(candidate, ExternalValueCandidate):
            self._apply_external_value(candidate)
            return
        if isinstance(candidate, IdentifierNameCandidate):
            self._apply_identifier_name(candidate)
            return
        raise TypeError(f"unsupported binding candidate: {type(candidate).__name__}")

    def build(self, *, unroll: bool | str = "auto") -> BasicComposable:
        """Build the current scope graph."""
        return self.builder.build(unroll=unroll)

    def _apply_composable(self, candidate: ComposableCandidate) -> None:
        resource = candidate.resource
        self.builder.add(
            resource.build_name,
            resource.composable,
            indexes=resource.build_index,
        )
        build_path = candidate.target_record.build_path.parts
        if not build_path:
            raise ValueError("target hole record must have a non-empty build path")
        owner, ref_path = self._owner_and_ref_path_for(candidate.target_record)
        self.builder.target(
            root_instance=owner,
            ref_path=ref_path,
            target_name=candidate.target_record.name.logical_name(),
        ).add(
            resource.build_name,
            indexes=resource.build_index,
            order=resource.order,
        )
        self._owner_by_build_prefix[build_path + (resource.instance_name,)] = (
            resource.instance_name
        )
        if _record_is_single_additive_hole_demand(candidate.target_record):
            self._mark_record_satisfied(candidate.target_record.record_id)
        self._replace_occurrence_inventory(
            build_path + (resource.instance_name,),
            resource.composable,
        )

    def _apply_external_value(self, candidate: ExternalValueCandidate) -> None:
        owner = self._owner_for(candidate.demand_record)
        composable = self._registered_basic(owner)
        rebound = composable.bind(
            {candidate.demand_record.name.logical_name(): candidate.resource.value}
        )
        self.builder.graph.replace_instance(owner, rebound)
        self._refresh_owner_occurrences(owner, rebound)

    def _apply_identifier_name(self, candidate: IdentifierNameCandidate) -> None:
        owner = self._owner_for(candidate.demand_record)
        composable = self._registered_basic(owner)
        rebound = composable.bind_identifier(
            {
                candidate.demand_record.name.logical_name(): (
                    candidate.resource.identifier
                )
            }
        )
        self.builder.graph.replace_instance(owner, rebound)
        self._refresh_owner_occurrences(owner, rebound)

    def _registered_basic(self, name: str) -> BasicComposable:
        for record in self.builder.graph.instances:
            if record.name != name:
                continue
            if not isinstance(record.composable, BasicComposable):
                raise TypeError(
                    "assembler candidate application requires BasicComposable "
                    f"instances; got {type(record.composable).__name__}"
                )
            return record.composable
        raise ValueError(f"unknown builder instance: {name}")

    def _owner_for(self, record: InventoryRecord) -> str:
        owner, _ = self._owner_and_ref_path_for(record)
        return owner

    def _owner_and_ref_path_for(
        self, record: InventoryRecord
    ) -> tuple[str, tuple[str | int, ...]]:
        path = record.build_path.parts
        for prefix, owner in sorted(
            self._owner_by_build_prefix.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if path[: len(prefix)] == prefix:
                return owner, _ref_path_from_build_parts(path[len(prefix) :])
        raise ValueError(f"no registered owner for build path `{record.build_path}`")

    def _refresh_owner_occurrences(
        self, owner: str, composable: Composable
    ) -> None:
        for prefix, prefix_owner in tuple(self._owner_by_build_prefix.items()):
            if prefix_owner == owner:
                self._replace_occurrence_inventory(prefix, composable)

    def _replace_occurrence_inventory(
        self,
        build_prefix: tuple[str, ...],
        composable: Composable,
    ) -> None:
        if not isinstance(composable, BasicComposable):
            raise TypeError(
                "assembler scope inventory requires BasicComposable instances; "
                f"got {type(composable).__name__}"
            )
        old_record_ids = self._record_ids_by_build_prefix.get(build_prefix, ())
        inventory = _without_record_ids(self._inventory, old_record_ids)
        prefixed = _prefixed_occurrence_inventory(build_prefix, composable)
        visible_record_ids: set[InventoryRecordId] = set()
        mutable = MutableInventory()
        for record in inventory.records.values():
            mutable.add_existing_record(record)
        for record in prefixed.records.values():
            if record.record_id in self._satisfied_record_ids:
                continue
            mutable.add_existing_record(record)
            visible_record_ids.add(record.record_id)
        self._record_ids_by_build_prefix[build_prefix] = frozenset(
            visible_record_ids
        )
        self._inventory = mutable.freeze()

    def _mark_record_satisfied(self, record_id: InventoryRecordId) -> None:
        self._satisfied_record_ids.add(record_id)
        self._inventory = _without_record_ids(self._inventory, (record_id,))
        for prefix, record_ids in tuple(self._record_ids_by_build_prefix.items()):
            if record_id in record_ids:
                self._record_ids_by_build_prefix[prefix] = frozenset(
                    item for item in record_ids if item != record_id
                )

    def _refresh_inventory_from_build(self) -> None:
        instances = self.builder.graph.instances
        if not instances:
            self._inventory = empty_inventory()
            return
        self._inventory = self.builder.build(unroll=False).inventory


def as_composable(
    composable: Composable,
    *,
    build_name: str,
    build_index: int | tuple[int, ...] | None = None,
    order: int = 0,
) -> ComposableResource:
    """Wrap a composable as a resource with the builder name it should use."""
    return ComposableResource(
        composable=composable,
        build_name=build_name,
        build_index=build_index,
        order=order,
    )


def as_external_value(value: ExternalValue) -> ExternalValueResource:
    """Wrap an external binding value as a resource."""
    return ExternalValueResource(value=value)


def as_identifier(identifier: str) -> IdentifierNameResource:
    """Wrap a Python identifier spelling as a resource."""
    return IdentifierNameResource(identifier=identifier)


def _ref_path_from_build_parts(parts: tuple[str, ...]) -> tuple[str | int, ...]:
    """Convert inventory build-path parts into builder descendant ref parts."""
    ref_path: list[str | int] = []
    for part in parts:
        parsed = parse_indexed_instance_name(part)
        if parsed is None:
            ref_path.append(part)
            continue
        stem, indexes = parsed
        ref_path.append(stem)
        ref_path.extend(indexes)
    return tuple(ref_path)


def _prefixed_occurrence_inventory(
    build_prefix: tuple[str, ...],
    composable: BasicComposable,
) -> Inventory:
    from astichi.materialize.api import _occurrence_inventory

    mutable = MutableInventory()
    mutable.add_inventory(
        ResourcePath(build_prefix),
        _occurrence_inventory(composable),
    )
    return mutable.freeze()


def _without_record_ids(
    inventory: Inventory,
    record_ids: Iterable[InventoryRecordId],
) -> Inventory:
    remove = frozenset(record_ids)
    if not remove:
        return inventory
    mutable = MutableInventory()
    for record in inventory.records.values():
        if record.record_id not in remove:
            mutable.add_existing_record(record)
    return mutable.freeze()


def find_candidates(
    inventory: Inventory,
    resource: BindingResource,
    *,
    name: str | None = None,
    build_match: tuple[str, ...] | None = None,
    owner_match: tuple[str, ...] | None = None,
) -> tuple[BindingCandidate, ...]:
    """Return binding candidates for ``resource`` in ``inventory``."""
    return resource.find_candidates(
        inventory,
        DemandSelector(
            name=name,
            build_match=build_match,
            owner_match=owner_match,
        ),
    )


def require_one(candidates: tuple[BindingCandidate, ...]) -> BindingCandidate:
    """Return the only candidate, or raise when matching is ambiguous/missing."""
    if len(candidates) == 1:
        return candidates[0]
    lines = [f"expected exactly one candidate, found {len(candidates)}"]
    for index, candidate in enumerate(candidates, start=1):
        lines.append(f"candidate {index}:")
        lines.extend(f"  {line}" for line in candidate.diagnostic_lines())
    raise ValueError("\n".join(lines))


def code_owner_parts(code_owner: CodePath) -> tuple[str, ...]:
    """Return code-owner logical names as a tuple for selector matching."""
    return tuple(node.logical_name() for node in code_owner.nodes)


def _records_for_map(
    inventory: Inventory,
    record_map: dict[str, tuple[str, ...]],
    selector: DemandSelector,
) -> tuple[InventoryRecord, ...]:
    if selector.name is None:
        record_ids = tuple(
            record_id
            for ids in record_map.values()
            for record_id in ids
        )
    else:
        record_ids = record_map.get(selector.name, ())
    return tuple(
        record
        for record in inventory.records_for_ids(record_ids)
        if _record_matches(record, selector)
    )


def _record_matches(record: InventoryRecord, selector: DemandSelector) -> bool:
    if selector.name is not None and record.name.logical_name() != selector.name:
        return False
    if selector.build_match is not None:
        if not matches_path(selector.build_match, record.build_path.parts):
            return False
    if selector.owner_match is not None:
        if not matches_path(selector.owner_match, code_owner_parts(record.code_owner)):
            return False
    return True


def _production_records(composable: Composable) -> tuple[InventoryRecord, ...]:
    inventory = _inventory_for(composable)
    record_ids = tuple(
        record_id
        for ids in inventory.production_map.values()
        for record_id in ids
    )
    return inventory.records_for_ids(record_ids)


def _inventory_for(composable: Composable) -> Inventory:
    inventory = getattr(composable, "inventory", None)
    if not isinstance(inventory, Inventory):
        raise TypeError(
            "assembler resources require composables with inventory metadata"
        )
    return inventory


def _hole_descriptor(record: InventoryRecord) -> HoleDescriptor | None:
    payload = record.payload
    if not isinstance(payload, PortInventoryPayload):
        return None
    port = payload.port
    if not isinstance(port, DemandPort):
        return None
    return HoleDescriptor(port=PortDescriptor.from_demand(port))


def _record_is_single_additive_hole_demand(record: InventoryRecord) -> bool:
    payload = record.payload
    if not isinstance(payload, PortInventoryPayload):
        return False
    port = payload.port
    if not isinstance(port, DemandPort):
        return False
    if not port.is_additive_hole_demand():
        return False
    return not (
        port.shape.is_block()
        or port.shape.is_positional_variadic()
        or port.shape.is_named_variadic()
        or port.shape.is_elif_clause()
    )


def _production_satisfies(
    production_record: InventoryRecord, hole: HoleDescriptor
) -> bool:
    production = _production_descriptor(production_record)
    if production is None:
        return False
    return production.satisfies(hole).is_accepted()


def _production_descriptor(record: InventoryRecord) -> ProductionDescriptor | None:
    payload = record.payload
    name = record.name.logical_name()
    if record.kind == "production.supply":
        if not isinstance(payload, PortInventoryPayload):
            return None
        port = payload.port
        if not isinstance(port, SupplyPort):
            return None
        return ProductionDescriptor(
            name=name,
            port=PortDescriptor.from_supply(port),
        )
    if record.kind == "production.elif":
        return elif_production(name)
    if isinstance(payload, FuncargsProductionInventoryPayload):
        return funcargs_production(payload.payload, name=name)
    if isinstance(payload, ExpressionProductionInventoryPayload):
        return expression_ast_production(payload.expression, name=name)
    if isinstance(payload, BlockProductionInventoryPayload):
        return block_production(name)
    return None


def _format_demand_record(record: InventoryRecord) -> str:
    return (
        f"build_path={record.build_path} "
        f"owner={_format_code_owner(record.code_owner)} "
        f"name={record.name.logical_name()} "
        f"kind={record.kind} "
        f"location={_format_location(record.source_location)} "
        f"locator={record.locator}"
    )


def _format_resource_record(record: InventoryRecord) -> str:
    return (
        f"name={record.name.logical_name()} "
        f"kind={record.kind} "
        f"location={_format_location(record.source_location)} "
        f"locator={record.locator}"
    )


def _format_code_owner(code_owner: CodePath) -> str:
    if not code_owner.nodes:
        return "."
    return "/".join(_format_code_owner_node(node) for node in code_owner.nodes)


def _format_code_owner_node(node: CodePathNode) -> str:
    return f"{node.logical_name()}@{_format_location(_code_owner_location(node))}"


def _code_owner_location(node: CodePathNode) -> SourceLocation | None:
    if isinstance(node, ClassCodePathNode):
        return _source_location_for_ast_node(node.class_ast_node)
    if isinstance(node, FunctionCodePathNode):
        return _source_location_for_ast_node(node.function_ast_node)
    return None


def _source_location_for_ast_node(node) -> SourceLocation | None:
    line_number = getattr(node, "lineno", None)
    if not isinstance(line_number, int):
        return None
    file_name = astichi_source_file(node) or "<astichi>"
    return SourceLocation(file_name=file_name, line_number=line_number)


def _format_location(location: SourceLocation | None) -> str:
    if location is None:
        return "<unknown>"
    return str(location)
