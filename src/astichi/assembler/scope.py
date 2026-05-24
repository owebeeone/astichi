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
from astichi.lower_engine import (
    LowerEngine,
    LowerTemplateBinding,
    LowerTemplateCache,
)
from astichi.lower_engine.handles import OccurrenceId, RecordId
from astichi.lower_engine.inventory import AssemblyState
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
from astichi.perf_counters import active_perf_counters, counted_perf_call

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
    _lower_engine: LowerEngine = field(default_factory=LowerEngine, init=False)
    _lower_cache: LowerTemplateCache = field(init=False)
    _lower_state: AssemblyState = field(init=False)
    _lower_occurrence_by_build_prefix: dict[tuple[str, ...], OccurrenceId] = field(
        default_factory=dict,
        init=False,
    )
    _lower_record_by_inventory_id: dict[InventoryRecordId, RecordId] = field(
        default_factory=dict,
        init=False,
    )
    _lower_record_ids_by_build_prefix: dict[tuple[str, ...], frozenset[RecordId]] = (
        field(default_factory=dict, init=False)
    )
    _lower_inventory_ids_by_build_prefix: dict[
        tuple[str, ...], frozenset[InventoryRecordId]
    ] = field(default_factory=dict, init=False)
    _lower_projection_by_record_id: dict[RecordId, InventoryRecord] = field(
        default_factory=dict,
        init=False,
    )

    def __post_init__(self) -> None:
        self._lower_cache = LowerTemplateCache(self._lower_engine)
        self._lower_state = self._lower_engine.new_state()
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
        prefixed = self._replace_occurrence_inventory((name,), composable)
        self._append_lower_occurrence(
            (name,),
            composable,
            prefixed_inventory=prefixed,
        )
        return handle

    def lower_structural_snapshot(self) -> dict[str, object]:
        """Return the lower-engine structural state for diagnostics/tests."""
        return self._lower_engine.structural_snapshot(self._lower_state)

    def project_lower_inventory(self) -> Inventory:
        """Project the visible lower state back to the slow debug inventory."""
        mutable = MutableInventory()
        for record_id, record in self._lower_projection_by_record_id.items():
            if record_id in self._lower_state.dead_records:
                continue
            if record_id in self._lower_state.satisfied_records:
                continue
            mutable.add_existing_record(record)
        return mutable.freeze()

    @counted_perf_call("candidate_lookup_lower")
    def find_candidates(
        self,
        resource: BindingResource,
        *,
        name: str | None = None,
        build_match: tuple[str, ...] | None = None,
        owner_match: tuple[str, ...] | None = None,
    ) -> tuple[BindingCandidate, ...]:
        """Return binding candidates from lower indexes without inventory projection."""
        selector = DemandSelector(
            name=name,
            build_match=build_match,
            owner_match=owner_match,
        )
        if isinstance(resource, ComposableResource):
            return self._find_lower_composable_candidates(resource, selector)
        if isinstance(resource, ExternalValueResource):
            return self._find_lower_external_candidates(resource, selector)
        if isinstance(resource, IdentifierNameResource):
            return self._find_lower_identifier_candidates(resource, selector)
        raise TypeError(f"unsupported binding resource: {type(resource).__name__}")

    @counted_perf_call("assembly_scope_apply")
    def apply(self, candidate: BindingCandidate) -> None:
        """Apply one candidate to the underlying builder graph."""
        counters = active_perf_counters()
        if isinstance(candidate, ComposableCandidate):
            if counters is not None:
                counters.increment("assembly_scope_apply_composable")
            self._apply_composable(candidate)
            return
        if isinstance(candidate, ExternalValueCandidate):
            if counters is not None:
                counters.increment("assembly_scope_apply_external_value")
            self._apply_external_value(candidate)
            return
        if isinstance(candidate, IdentifierNameCandidate):
            if counters is not None:
                counters.increment("assembly_scope_apply_identifier_name")
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
            self._mark_lower_record_satisfied(candidate.target_record.record_id)
        target_lower_record = self._lower_record_by_inventory_id.get(
            candidate.target_record.record_id
        )
        prefixed = self._replace_occurrence_inventory(
            build_path + (resource.instance_name,),
            resource.composable,
        )
        source_occurrence = self._append_lower_occurrence(
            build_path + (resource.instance_name,),
            resource.composable,
            parent_occurrence_id=self._lower_occurrence_by_build_prefix.get(build_path),
            prefixed_inventory=prefixed,
        )
        if target_lower_record is not None:
            self._lower_engine.append_edge(
                self._lower_state,
                target_record_id=target_lower_record,
                source_occurrence_id=source_occurrence,
                operation_key=_operation_key_for_target(candidate.target_record),
                order=resource.order,
            )

    def _apply_external_value(self, candidate: ExternalValueCandidate) -> None:
        self._append_lower_overlay(
            candidate.demand_record,
            kind="external",
            source_label=candidate.demand_record.name.logical_name(),
        )
        owner = self._owner_for(candidate.demand_record)
        composable = self._registered_basic(owner)
        rebound = composable.bind(
            {candidate.demand_record.name.logical_name(): candidate.resource.value}
        )
        self.builder.graph.replace_instance(owner, rebound)
        self._refresh_owner_occurrences(owner, rebound)

    def _apply_identifier_name(self, candidate: IdentifierNameCandidate) -> None:
        self._append_lower_overlay(
            candidate.demand_record,
            kind="identifier",
            source_label=candidate.resource.identifier,
        )
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
                prefixed = self._replace_occurrence_inventory(prefix, composable)
                self._append_lower_occurrence(
                    prefix,
                    composable,
                    prefixed_inventory=prefixed,
                )

    @counted_perf_call("replace_occurrence_inventory")
    def _replace_occurrence_inventory(
        self,
        build_prefix: tuple[str, ...],
        composable: Composable,
    ) -> Inventory:
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
        return prefixed

    def _mark_record_satisfied(self, record_id: InventoryRecordId) -> None:
        self._satisfied_record_ids.add(record_id)
        self._inventory = _without_record_ids(self._inventory, (record_id,))
        for prefix, record_ids in tuple(self._record_ids_by_build_prefix.items()):
            if record_id in record_ids:
                self._record_ids_by_build_prefix[prefix] = frozenset(
                    item for item in record_ids if item != record_id
                )

    def _append_lower_occurrence(
        self,
        build_prefix: tuple[str, ...],
        composable: Composable,
        *,
        parent_occurrence_id: OccurrenceId | None = None,
        prefixed_inventory: Inventory | None = None,
    ) -> OccurrenceId:
        if not isinstance(composable, BasicComposable):
            raise TypeError(
                "assembler scope lower state requires BasicComposable instances; "
                f"got {type(composable).__name__}"
            )
        binding = composable._lower_template
        if not isinstance(binding, LowerTemplateBinding):
            raise TypeError("BasicComposable is missing lower template metadata")

        self._remove_lower_prefix_records(build_prefix)
        template_id = self._lower_cache.template_id_for(binding)
        occurrence_id = self._lower_engine.append_occurrence(
            self._lower_state,
            template_id,
            build_path=build_prefix,
            parent_occurrence_id=parent_occurrence_id,
        )
        self._lower_occurrence_by_build_prefix[build_prefix] = occurrence_id
        lower_record_ids: set[RecordId] = set()
        inventory_record_ids: set[InventoryRecordId] = set()
        for index, spec in enumerate(binding.record_specs):
            if not spec.legacy_record_id:
                continue
            record_id = self._lower_engine.record_id(
                self._lower_state,
                occurrence_id,
                index,
            )
            lower_record_ids.add(record_id)
            inventory_record_id = _prefix_inventory_record_id(
                build_prefix,
                spec.legacy_record_id,
            )
            inventory_record_ids.add(inventory_record_id)
            self._lower_record_by_inventory_id[inventory_record_id] = record_id
            projection_record = _projection_record_for(
                prefixed_inventory,
                inventory_record_id,
            )
            if projection_record is not None:
                self._lower_projection_by_record_id[record_id] = projection_record
        self._lower_record_ids_by_build_prefix[build_prefix] = frozenset(
            lower_record_ids
        )
        self._lower_inventory_ids_by_build_prefix[build_prefix] = frozenset(
            inventory_record_ids
        )
        return occurrence_id

    def _remove_lower_prefix_records(self, build_prefix: tuple[str, ...]) -> None:
        old_lower_records = self._lower_record_ids_by_build_prefix.get(
            build_prefix,
            frozenset(),
        )
        for record_id in old_lower_records:
            self._lower_state.dead_records.add(record_id)
            self._lower_projection_by_record_id.pop(record_id, None)
        for inventory_id in self._lower_inventory_ids_by_build_prefix.get(
            build_prefix,
            frozenset(),
        ):
            self._lower_record_by_inventory_id.pop(inventory_id, None)

    def _mark_lower_record_satisfied(
        self,
        inventory_record_id: InventoryRecordId,
    ) -> None:
        record_id = self._lower_record_by_inventory_id.get(inventory_record_id)
        if record_id is not None:
            self._lower_engine.mark_satisfied(self._lower_state, record_id)

    def _append_lower_overlay(
        self,
        demand_record: InventoryRecord,
        *,
        kind: str,
        source_label: str,
    ) -> None:
        record_id = self._lower_record_by_inventory_id.get(demand_record.record_id)
        if record_id is None:
            return
        self._lower_engine.append_overlay(
            self._lower_state,
            kind=kind,
            source_label=source_label,
            target_record_id=record_id,
        )
        self._lower_engine.mark_satisfied(self._lower_state, record_id)

    def _find_lower_composable_candidates(
        self,
        resource: ComposableResource,
        selector: DemandSelector,
    ) -> tuple[BindingCandidate, ...]:
        production_records = _production_records(resource.composable)
        candidates: list[BindingCandidate] = []
        for target_record in self._lower_records_for_selector(
            selector,
            inventory_kinds=_lower_hole_inventory_kinds(),
        ):
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
                    resource=resource,
                    compatible_productions=compatible,
                )
            )
        return tuple(candidates)

    def _find_lower_external_candidates(
        self,
        resource: ExternalValueResource,
        selector: DemandSelector,
    ) -> tuple[BindingCandidate, ...]:
        return tuple(
            ExternalValueCandidate(demand_record=record, resource=resource)
            for record in self._lower_records_for_selector(
                selector,
                inventory_kinds=("external.bind",),
            )
        )

    def _find_lower_identifier_candidates(
        self,
        resource: IdentifierNameResource,
        selector: DemandSelector,
    ) -> tuple[BindingCandidate, ...]:
        return tuple(
            IdentifierNameCandidate(demand_record=record, resource=resource)
            for record in self._lower_records_for_selector(
                selector,
                inventory_kinds=("identifier.demand",),
            )
        )

    def _lower_records_for_selector(
        self,
        selector: DemandSelector,
        *,
        inventory_kinds: tuple[str, ...],
    ) -> tuple[InventoryRecord, ...]:
        record_ids = self._lower_candidate_record_ids(
            selector,
            inventory_kinds=inventory_kinds,
        )
        records: list[InventoryRecord] = []
        seen: set[RecordId] = set()
        for record_id in record_ids:
            if record_id in seen:
                continue
            seen.add(record_id)
            record = self._visible_lower_projection_record(record_id)
            if record is None:
                continue
            if record.kind not in inventory_kinds:
                continue
            if not _record_matches(record, selector):
                continue
            records.append(record)
        return tuple(records)

    def _lower_candidate_record_ids(
        self,
        selector: DemandSelector,
        *,
        inventory_kinds: tuple[str, ...],
    ) -> tuple[RecordId, ...]:
        indexes = self._lower_state.indexes
        if selector.name is not None:
            return tuple(indexes.by_resource_name.get(selector.name, ()))
        return tuple(
            record_id
            for kind in inventory_kinds
            for record_id in indexes.by_inventory_kind.get(kind, ())
        )

    def _visible_lower_projection_record(
        self,
        record_id: RecordId,
    ) -> InventoryRecord | None:
        if record_id in self._lower_state.dead_records:
            return None
        if record_id in self._lower_state.satisfied_records:
            return None
        return self._lower_projection_by_record_id.get(record_id)

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


def _prefix_inventory_record_id(
    build_prefix: tuple[str, ...],
    record_id: InventoryRecordId,
) -> InventoryRecordId:
    if not build_prefix:
        return record_id
    return "/".join(build_prefix + (record_id,))


def _operation_key_for_target(record: InventoryRecord) -> str:
    if record.kind == "hole.expr":
        return "astichi.operation.replace_expression"
    if record.kind == "hole.block":
        return "astichi.operation.splice_body_at_marker"
    if record.kind == "hole.params":
        return "astichi.operation.splice_parameters"
    if record.kind == "hole.elif":
        return "astichi.operation.append_clause"
    if record.kind.startswith("hole."):
        return "astichi.operation.splice_call_arguments"
    return "astichi.operation.append_body"


def _lower_hole_inventory_kinds() -> tuple[str, ...]:
    return (
        "hole.block",
        "hole.expr",
        "hole.params",
        "hole.elif",
        "hole.positional_variadic",
        "hole.named_variadic",
    )


def _projection_record_for(
    inventory: Inventory | None,
    record_id: InventoryRecordId,
) -> InventoryRecord | None:
    if inventory is None:
        return None
    return inventory.records.get(record_id)


@counted_perf_call("inventory_projection")
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


@counted_perf_call("candidate_lookup")
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
