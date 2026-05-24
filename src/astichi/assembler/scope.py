"""Inventory-driven assembly scope helpers."""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TypeAlias

from astichi.ast_provenance import astichi_source_file
from astichi.asttools import clone_ast, import_statement_binding_names
from astichi.builder.graph import (
    format_indexed_instance_name,
    parse_indexed_instance_name,
)
from astichi.builder.handles import BuilderHandle, InstanceHandle
from astichi.lower_engine import (
    HygieneOperation,
    LowerEngine,
    LowerTemplateBinding,
    LowerTemplateCache,
    MaterializationPlan,
    TemplateRecordSpec,
)
from astichi.lower_engine.handles import OccurrenceId, OverlayId, RecordId
from astichi.lower_engine.inventory import AssemblyState
from astichi.lower_engine.materialization import MaterializationOperation
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
    StaticResourceName,
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
            for record in _records_for_map(
                inventory, inventory.identifier_map, selector
            )
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


@dataclass(frozen=True, eq=False)
class _ResolvedCodePathNode(CodePathNode):
    """Code-owner node with an overlay-resolved visible name."""

    name: str
    source_location: SourceLocation | None

    def logical_name(self) -> str:
        return self.name


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
    _pending_external_binds_by_owner: dict[str, dict[str, object]] = field(
        default_factory=dict,
        init=False,
    )
    _pending_identifier_binds_by_owner: dict[str, dict[str, str]] = field(
        default_factory=dict,
        init=False,
    )
    _identifier_bindings_by_occurrence: dict[OccurrenceId, dict[str, str]] = field(
        default_factory=dict,
        init=False,
    )
    _lower_composable_by_occurrence: dict[OccurrenceId, BasicComposable] = field(
        default_factory=dict,
        init=False,
    )
    _external_value_by_overlay: dict[OverlayId, object] = field(
        default_factory=dict,
        init=False,
    )
    _identifier_value_by_overlay: dict[OverlayId, str] = field(
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
        return self.project_lower_inventory()

    def add(self, name: str, composable: Composable) -> InstanceHandle:
        """Register a root composable in this scope."""
        handle = self.builder.add(name, composable)
        self._owner_by_build_prefix[(name,)] = name
        self._append_lower_occurrence((name,), composable)
        return handle

    def lower_materialization_plan(self) -> MaterializationPlan:
        """Return the lower-owned materialization plan for diagnostics/tests."""
        plan = self._lower_engine.build_materialization_plan(self._lower_state)
        plan = self._append_lower_boundary_hygiene(plan)
        return self._append_lower_pyimport_hygiene(plan)

    def lower_structural_snapshot(
        self,
        *,
        materialization_plan: MaterializationPlan | None = None,
    ) -> dict[str, object]:
        """Return the lower-engine structural state for diagnostics/tests."""
        return self._lower_engine.structural_snapshot(
            self._lower_state,
            materialization_plan=materialization_plan,
        )

    @counted_perf_call("debug_inventory_projection")
    def project_lower_inventory(self) -> Inventory:
        """Project the visible lower state back to the slow debug inventory."""
        mutable = MutableInventory()
        for record_id, record in self._lower_projection_by_record_id.items():
            resolved = self._visible_lower_projection_record(record_id)
            if resolved is not None:
                mutable.add_existing_record(resolved)
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
        materialized = None
        if unroll in ("auto", False):
            materialized = self._lower_materialize_if_supported()
        counters = active_perf_counters()
        if materialized is not None:
            if counters is not None:
                counters.increment("lower_build_selection")
                counters.increment("lower_materialization_artifact")
            return materialized
        if counters is not None:
            counters.increment("lower_materialization_adapter_fallback")
        return self._build_with_adapter(unroll=unroll)

    def _build_with_adapter(self, *, unroll: bool | str = "auto") -> BasicComposable:
        self._flush_pending_identifier_binds()
        self._flush_pending_external_binds()
        return self.builder.build(unroll=unroll)

    @counted_perf_call("lower_materialize")
    def lower_materialize(self) -> BasicComposable:
        """Materialize the currently supported lower-owned subset."""
        materialized = self._lower_materialize_if_supported()
        counters = active_perf_counters()
        if materialized is None:
            if counters is not None:
                counters.increment("lower_materialization_adapter_fallback")
            return self._build_with_adapter().materialize()
        if counters is not None:
            counters.increment("lower_materialization_artifact")
        return materialized

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
        source_occurrence = self._append_lower_occurrence(
            build_path + (resource.instance_name,),
            resource.composable,
            parent_occurrence_id=self._lower_occurrence_by_build_prefix.get(build_path),
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
        appended = self._append_lower_overlay(
            candidate.demand_record,
            kind="external",
            source_label=candidate.demand_record.name.logical_name(),
        )
        if appended is not None:
            _, overlay_id = appended
            self._external_value_by_overlay[overlay_id] = candidate.resource.value
        owner = self._owner_for(candidate.demand_record)
        self._queue_external_bind(
            owner,
            candidate.demand_record.name.logical_name(),
            candidate.resource.value,
        )

    def _apply_identifier_name(self, candidate: IdentifierNameCandidate) -> None:
        appended = self._append_lower_overlay(
            candidate.demand_record,
            kind="identifier",
            source_label=candidate.resource.identifier,
        )
        record_id = None
        if appended is not None:
            record_id, overlay_id = appended
            self._identifier_value_by_overlay[overlay_id] = (
                candidate.resource.identifier
            )
        owner = self._owner_for(candidate.demand_record)
        authored_name = candidate.demand_record.name.logical_name()
        if record_id is not None:
            self._identifier_bindings_by_occurrence.setdefault(
                record_id.occurrence_id,
                {},
            )[authored_name] = candidate.resource.identifier
        self._queue_identifier_bind(
            owner,
            authored_name,
            candidate.resource.identifier,
        )

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

    def _refresh_owner_occurrences(self, owner: str, composable: Composable) -> None:
        for prefix, prefix_owner in tuple(self._owner_by_build_prefix.items()):
            if prefix_owner == owner:
                self._append_lower_occurrence(prefix, composable)

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
        self._record_ids_by_build_prefix[build_prefix] = frozenset(visible_record_ids)
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
        self._lower_composable_by_occurrence[occurrence_id] = composable
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
            projection_record = _projection_record_for(build_prefix, spec)
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
    ) -> tuple[RecordId, OverlayId] | None:
        record_id = self._lower_record_by_inventory_id.get(demand_record.record_id)
        if record_id is None:
            return None
        overlay_id = self._lower_engine.append_overlay(
            self._lower_state,
            kind=kind,
            source_label=source_label,
            target_record_id=record_id,
        )
        self._lower_engine.mark_satisfied(self._lower_state, record_id)
        return record_id, overlay_id

    def _try_lower_materialize_expression_overlay_subset(
        self,
        plan: MaterializationPlan,
    ) -> BasicComposable | None:
        root_id = plan.root_occurrence_id
        if root_id is None:
            return None
        root = self._lower_composable_by_occurrence.get(root_id)
        if root is None:
            return None
        tree = clone_ast(root.tree)
        identifier_bindings: dict[str, str] = {}
        external_bindings: dict[str, object] = {}
        expression_operations: list[MaterializationOperation] = []
        block_operations: list[MaterializationOperation] = []
        parameter_operations: list[MaterializationOperation] = []
        elif_operations: list[MaterializationOperation] = []
        call_argument_operations: list[MaterializationOperation] = []
        for operation in plan.operation_stream:
            if operation.target_record_id.occurrence_id != root_id:
                return None
            if operation.operation_key == "astichi.operation.rewrite_identifier":
                if not self._collect_identifier_operation(
                    operation,
                    identifier_bindings,
                ):
                    return None
                continue
            if operation.operation_key == "astichi.operation.lower_external_ref":
                if not self._collect_external_operation(
                    operation,
                    external_bindings,
                ):
                    return None
                continue
            if operation.operation_key == "astichi.operation.replace_expression":
                expression_operations.append(operation)
                continue
            if operation.operation_key == "astichi.operation.splice_body_at_marker":
                block_operations.append(operation)
                continue
            if operation.operation_key == "astichi.operation.splice_parameters":
                parameter_operations.append(operation)
                continue
            if operation.operation_key == "astichi.operation.append_clause":
                elif_operations.append(operation)
                continue
            if operation.operation_key == "astichi.operation.splice_call_arguments":
                call_argument_operations.append(operation)
                continue
            return None

        if identifier_bindings:
            from astichi.materialize.api import (
                _resolve_arg_identifiers,
                _resolve_boundary_imports,
                _resolve_boundary_passes,
            )

            _resolve_arg_identifiers(tree, identifier_bindings)
            _resolve_boundary_imports(tree, identifier_bindings)
            _resolve_boundary_passes(tree, identifier_bindings)
        if external_bindings:
            from astichi.lowering import apply_external_bindings

            apply_external_bindings(tree, external_bindings)
        for operation in expression_operations:
            if not self._apply_lower_expression_operation(tree, operation):
                return None
        if block_operations and not self._apply_lower_block_operations(
            tree,
            block_operations,
        ):
            return None
        if parameter_operations and not self._apply_lower_parameter_operations(
            tree,
            parameter_operations,
        ):
            return None
        if elif_operations and not self._apply_lower_elif_operations(
            tree,
            elif_operations,
        ):
            return None
        if call_argument_operations and not self._apply_lower_call_argument_operations(
            tree,
            call_argument_operations,
        ):
            return None
        _strip_lower_boundary_markers(tree)
        _strip_lower_keep_markers(tree)
        if not self._apply_lower_managed_pyimports(tree):
            return None
        ast.fix_missing_locations(tree)
        from astichi.model.basic import _rebuild_composable

        materialized = _rebuild_composable(
            tree=tree,
            origin=root.origin,
            bound_externals=frozenset(),
        )
        if _has_unresolved_lower_astichi_demands(materialized):
            return None
        return materialized

    def _lower_materialize_if_supported(self) -> BasicComposable | None:
        return self._try_lower_materialize_expression_overlay_subset(
            self.lower_materialization_plan()
        )

    def _append_lower_pyimport_hygiene(
        self,
        plan: MaterializationPlan,
    ) -> MaterializationPlan:
        root_id = plan.root_occurrence_id
        if root_id is None:
            return plan
        root = self._lower_composable_by_occurrence.get(root_id)
        if root is None:
            return plan
        try:
            from astichi.materialize.pyimport import collect_managed_imports

            records = collect_managed_imports(root.markers)
        except ValueError:
            return plan
        if not records:
            return plan
        hygiene = tuple(
            HygieneOperation(
                operation_key="astichi.operation.managed_import_request",
                target_scope_id=0,
                captures={
                    "final_local_name": record.final_local_name,
                    "module_path": ".".join(record.module_path),
                    "original_symbol": record.original_symbol,
                    "root_occurrence_id": root_id.index,
                },
            )
            for record in records
        )
        return MaterializationPlan(
            root_occurrence_id=plan.root_occurrence_id,
            operation_stream=plan.operation_stream,
            hygiene_stream=hygiene + plan.hygiene_stream,
            debug_views={
                **plan.debug_views,
                "managed_import_request_count": len(hygiene),
            },
            artifact_requests=plan.artifact_requests,
        )

    def _append_lower_boundary_hygiene(
        self,
        plan: MaterializationPlan,
    ) -> MaterializationPlan:
        hygiene: list[HygieneOperation] = []
        for operation in plan.operation_stream:
            source_id = operation.source_occurrence_id
            if source_id is None:
                continue
            if operation.operation_key != "astichi.operation.splice_body_at_marker":
                continue
            source = self._lower_composable_by_occurrence.get(source_id)
            if source is None or source.classification is None:
                continue
            target = self._lower_composable_by_occurrence.get(
                operation.target_record_id.occurrence_id
            )
            if target is None:
                continue
            target_locator = self._lower_engine.locator_for_record(
                self._lower_state,
                operation.target_record_id,
            )
            target_statement_path = _block_statement_path_for_locator(
                target.tree,
                target_locator.ast_path,
            )
            boundary_names = _lower_boundary_available_names(
                target.tree,
                target_statement_path,
            )
            collisions = tuple(sorted(boundary_names & source.classification.locals))
            if not collisions:
                continue
            hygiene.append(
                HygieneOperation(
                    operation_key="astichi.operation.rename_if_collides",
                    target_scope_id=0,
                    record_id=operation.target_record_id,
                    captures={
                        "colliding_names": list(collisions),
                        "source_occurrence_id": source_id.index,
                    },
                )
            )
        for occurrence_id, composable in self._lower_composable_by_occurrence.items():
            if not self._lower_engine.occurrence(self._lower_state, occurrence_id).live:
                continue
            for marker in composable.markers:
                if marker.source_name not in {
                    "astichi_export",
                    "astichi_import",
                    "astichi_keep",
                    "astichi_pass",
                }:
                    continue
                hygiene.append(
                    HygieneOperation(
                        operation_key=(
                            "astichi.operation.keep_name"
                            if marker.source_name == "astichi_keep"
                            else "astichi.operation.strip_marker"
                        ),
                        target_scope_id=0,
                        captures={
                            "marker": marker.source_name,
                            "name": marker.name_id,
                            "occurrence_id": occurrence_id.index,
                        },
                    )
                )
        if not hygiene:
            return plan
        return MaterializationPlan(
            root_occurrence_id=plan.root_occurrence_id,
            operation_stream=plan.operation_stream,
            hygiene_stream=tuple(hygiene) + plan.hygiene_stream,
            debug_views={
                **plan.debug_views,
                "boundary_marker_count": len(hygiene),
            },
            artifact_requests=plan.artifact_requests,
        )

    def _collect_identifier_operation(
        self,
        operation: MaterializationOperation,
        bindings: dict[str, str],
    ) -> bool:
        if operation.overlay_id is None:
            return False
        value = self._identifier_value_by_overlay.get(operation.overlay_id)
        if value is None:
            return False
        record = self._lower_engine.template_record(
            self._lower_state,
            operation.target_record_id,
        )
        bindings[record.resource_name] = value
        return True

    def _collect_external_operation(
        self,
        operation: MaterializationOperation,
        bindings: dict[str, object],
    ) -> bool:
        if operation.overlay_id is None:
            return False
        if operation.overlay_id not in self._external_value_by_overlay:
            return False
        record = self._lower_engine.template_record(
            self._lower_state,
            operation.target_record_id,
        )
        bindings[record.resource_name] = self._external_value_by_overlay[
            operation.overlay_id
        ]
        return True

    def _apply_lower_managed_pyimports(self, tree: ast.Module) -> bool:
        from astichi.lowering import apply_external_ref_lowering, recognize_markers
        from astichi.materialize.pyimport import (
            collect_managed_imports,
            has_pyimport_marker,
            insert_managed_imports,
        )

        try:
            apply_external_ref_lowering(tree)
            markers = recognize_markers(tree)
            if not has_pyimport_marker(markers):
                return True
            marker_call_ids = {
                id(marker.node)
                for marker in markers
                if marker.source_name == "astichi_pyimport"
            }
            if not marker_call_ids <= _module_pyimport_call_ids(tree):
                return False
            records = collect_managed_imports(markers)
        except ValueError:
            return False
        if not records:
            return False
        if _lower_pyimport_collides_with_existing_bindings(tree, records):
            return False
        insert_managed_imports(tree, records)
        _strip_lower_pyimport_declarations(tree)
        return not has_pyimport_marker(recognize_markers(tree))

    def _apply_lower_expression_operation(
        self,
        tree: ast.Module,
        operation: MaterializationOperation,
    ) -> bool:
        source_id = operation.source_occurrence_id
        if source_id is None:
            return False
        source = self._lower_composable_by_occurrence.get(source_id)
        if source is None:
            return False
        source_path = self._source_expression_path(source_id)
        if source_path is None:
            return False
        replacement = clone_ast(_ast_node_at_path(source.tree, source_path))
        if not isinstance(replacement, ast.expr):
            return False
        target_locator = self._lower_engine.locator_for_record(
            self._lower_state,
            operation.target_record_id,
        )
        _replace_ast_node_at_path(tree, target_locator.ast_path, replacement)
        return True

    def _apply_lower_block_operations(
        self,
        tree: ast.Module,
        operations: list[MaterializationOperation],
    ) -> bool:
        for target_record_id in _ordered_unique_operation_targets(operations):
            target_locator = self._lower_engine.locator_for_record(
                self._lower_state,
                target_record_id,
            )
            target_statement_path = _block_statement_path_for_locator(
                tree,
                target_locator.ast_path,
            )
            boundary_names = _lower_boundary_available_names(
                tree,
                target_statement_path,
            )
            ordered = sorted(
                (
                    operation
                    for operation in operations
                    if operation.target_record_id == target_record_id
                ),
                key=lambda operation: (
                    operation.order,
                    int(operation.captures.get("edge_id", 0)),
                ),
            )
            statements: list[ast.stmt] = []
            emitted_names: set[str] = set(boundary_names)
            rename_counter = 1
            for operation in ordered:
                source_id = operation.source_occurrence_id
                if source_id is None and operation.captures.get("fallback_selected"):
                    fallback_node = _ast_node_at_path(tree, target_locator.ast_path)
                    if not isinstance(fallback_node, ast.With):
                        return False
                    statements.extend(clone_ast(fallback_node.body))
                    continue
                if source_id is None:
                    return False
                source = self._lower_composable_by_occurrence.get(source_id)
                if source is None:
                    return False
                if not self._has_single_block_production(source_id):
                    return False
                if source.markers and not _lower_boundary_markers_supported(
                    source,
                    boundary_names,
                ):
                    return False
                source_locals = (
                    frozenset()
                    if source.classification is None
                    else source.classification.locals
                )
                collisions = emitted_names & source_locals
                if collisions and source.keep_names:
                    return False
                rename_map: dict[str, str] = {}
                for name in sorted(collisions):
                    next_name, rename_counter = _fresh_lower_scoped_name(
                        name,
                        emitted_names | set(source_locals) | set(rename_map.values()),
                        rename_counter,
                    )
                    rename_map[name] = next_name
                source_statements = clone_ast(source.tree.body)
                if rename_map:
                    _rename_lower_names(source_statements, rename_map)
                emitted_names.update(source_locals - collisions)
                emitted_names.update(rename_map.values())
                statements.extend(source_statements)
            _replace_ast_statement_at_path(
                tree,
                target_statement_path,
                statements,
            )
        return True

    def _apply_lower_parameter_operations(
        self,
        tree: ast.Module,
        operations: list[MaterializationOperation],
    ) -> bool:
        from astichi.materialize.api import _merge_params_into_arguments

        for target_record_id in _ordered_unique_operation_targets(operations):
            target_record = self._lower_engine.template_record(
                self._lower_state,
                target_record_id,
            )
            target_locator = self._lower_engine.locator_for_record(
                self._lower_state,
                target_record_id,
            )
            function_path = _function_path_for_parameter_locator(
                target_locator.ast_path,
            )
            if function_path is None:
                return False
            function_node = _ast_node_at_path(tree, function_path)
            if not isinstance(function_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
            payloads: list[ast.arguments] = []
            ordered = sorted(
                (
                    operation
                    for operation in operations
                    if operation.target_record_id == target_record_id
                ),
                key=lambda operation: (
                    operation.order,
                    int(operation.captures.get("edge_id", 0)),
                ),
            )
            for operation in ordered:
                source_id = operation.source_occurrence_id
                if source_id is None:
                    return False
                source = self._lower_composable_by_occurrence.get(source_id)
                if source is None:
                    return False
                payload_path = self._source_parameter_path(source_id)
                if payload_path is None:
                    return False
                payload_node = _ast_node_at_path(source.tree, payload_path)
                if not isinstance(
                    payload_node,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    return False
                payloads.append(clone_ast(payload_node.args))
            function_node.args = _merge_params_into_arguments(
                function_node.args,
                {target_record.resource_name: payloads},
            )
        return True

    def _apply_lower_elif_operations(
        self,
        tree: ast.Module,
        operations: list[MaterializationOperation],
    ) -> bool:
        for target_record_id in _ordered_unique_operation_targets(operations):
            target_record = self._lower_engine.template_record(
                self._lower_state,
                target_record_id,
            )
            target_locator = self._lower_engine.locator_for_record(
                self._lower_state,
                target_record_id,
            )
            marker_if_path = _if_statement_path_for_elif_locator(
                target_locator.ast_path,
            )
            if marker_if_path is None:
                return False
            marker_if = _ast_node_at_path(tree, marker_if_path)
            if not isinstance(marker_if, ast.If):
                return False
            boundary_names = _lower_boundary_available_names(tree, marker_if_path)
            chain_tail = clone_ast(marker_if.orelse)
            payloads: list[ast.If] = []
            ordered = sorted(
                (
                    operation
                    for operation in operations
                    if operation.target_record_id == target_record_id
                ),
                key=lambda operation: (
                    operation.order,
                    int(operation.captures.get("edge_id", 0)),
                ),
            )
            for operation in ordered:
                source_id = operation.source_occurrence_id
                if source_id is None:
                    return False
                source = self._lower_composable_by_occurrence.get(source_id)
                if source is None:
                    return False
                payload_path = self._source_elif_path(source_id)
                if payload_path is None:
                    return False
                payload_node = _ast_node_at_path(source.tree, payload_path)
                if not isinstance(payload_node, ast.FunctionDef):
                    return False
                if source.markers and not _lower_boundary_markers_supported(
                    source,
                    boundary_names,
                ):
                    return False
                payload_if = _single_lower_elif_payload_if(payload_node)
                if payload_if is None:
                    return False
                if not target_record.code_owner_parts and _body_contains_return(
                    payload_if.body
                ):
                    return False
                payloads.append(payload_if)
            chain = chain_tail
            for payload_if in reversed(payloads):
                branch = ast.If(
                    test=clone_ast(payload_if.test),
                    body=clone_ast(payload_if.body),
                    orelse=chain,
                )
                ast.copy_location(branch, marker_if)
                chain = [branch]
            _replace_ast_statement_at_path(tree, marker_if_path, chain)
        return True

    def _apply_lower_call_argument_operations(
        self,
        tree: ast.Module,
        operations: list[MaterializationOperation],
    ) -> bool:
        from astichi.lowering.call_argument_payloads import (
            DOUBLE_STAR_FUNC_ARG_REGION,
            STARRED_FUNC_ARG_REGION,
            extract_funcargs_payload,
            lower_payload_for_region,
            payload_explicit_keyword_names,
            register_explicit_keyword,
            validate_payload_for_region,
        )

        for target_record_id in _ordered_unique_operation_targets(operations):
            target_record = self._lower_engine.template_record(
                self._lower_state,
                target_record_id,
            )
            target_locator = self._lower_engine.locator_for_record(
                self._lower_state,
                target_record_id,
            )
            placement = _call_argument_placement_for_locator(
                target_locator.ast_path,
                target_record.inventory_kind,
            )
            if placement is None:
                return False
            call_node = _ast_node_at_path(tree, placement.call_path)
            if not isinstance(call_node, ast.Call):
                return False
            ordered = sorted(
                (
                    operation
                    for operation in operations
                    if operation.target_record_id == target_record_id
                ),
                key=lambda operation: (
                    operation.order,
                    int(operation.captures.get("edge_id", 0)),
                ),
            )
            lowered_args: list[ast.expr] = []
            lowered_keywords: list[ast.keyword] = []
            seen_explicit_keywords: set[str] = set()
            for operation in ordered:
                source_id = operation.source_occurrence_id
                if source_id is None:
                    return False
                source = self._lower_composable_by_occurrence.get(source_id)
                if source is None:
                    return False
                payload_path = self._source_funcargs_path(source_id)
                if payload_path is None:
                    return False
                payload_call = _ast_node_at_path(source.tree, payload_path)
                if not isinstance(payload_call, ast.Call):
                    return False
                payload = extract_funcargs_payload(payload_call)
                if placement.region_name == "starred":
                    validate_payload_for_region(
                        payload,
                        region=STARRED_FUNC_ARG_REGION,
                        hole_name=target_record.resource_name,
                    )
                    args, _ = lower_payload_for_region(
                        payload,
                        region=STARRED_FUNC_ARG_REGION,
                        hole_name=target_record.resource_name,
                        transform_expr=clone_ast,
                    )
                    lowered_args.extend(args)
                    continue
                for name in payload_explicit_keyword_names(payload):
                    register_explicit_keyword(name, seen_explicit_keywords)
                validate_payload_for_region(
                    payload,
                    region=DOUBLE_STAR_FUNC_ARG_REGION,
                    hole_name=target_record.resource_name,
                )
                _, keywords = lower_payload_for_region(
                    payload,
                    region=DOUBLE_STAR_FUNC_ARG_REGION,
                    hole_name=target_record.resource_name,
                    transform_expr=clone_ast,
                )
                lowered_keywords.extend(keywords)
            if placement.region_name == "starred":
                call_node.args[placement.index : placement.index + 1] = lowered_args
                continue
            call_node.keywords[placement.index : placement.index + 1] = lowered_keywords
        return True

    def _source_expression_path(self, occurrence_id: OccurrenceId) -> str | None:
        records = self._lower_engine.template_records_for_occurrence(
            self._lower_state,
            occurrence_id,
        )
        matches = tuple(
            record
            for record in records
            if record.surface_key == "astichi.surface.expression.production"
        )
        if len(matches) != 1:
            return None
        record_id = RecordId(
            occurrence_id=occurrence_id,
            template_record_id=matches[0].template_record_id,
        )
        return self._lower_engine.locator_for_record(
            self._lower_state,
            record_id,
        ).ast_path

    def _source_parameter_path(self, occurrence_id: OccurrenceId) -> str | None:
        records = self._lower_engine.template_records_for_occurrence(
            self._lower_state,
            occurrence_id,
        )
        matches = tuple(
            record
            for record in records
            if record.surface_key == "astichi.surface.parameter.production"
        )
        if len(matches) != 1:
            return None
        record_id = RecordId(
            occurrence_id=occurrence_id,
            template_record_id=matches[0].template_record_id,
        )
        return self._lower_engine.locator_for_record(
            self._lower_state,
            record_id,
        ).ast_path

    def _source_elif_path(self, occurrence_id: OccurrenceId) -> str | None:
        records = self._lower_engine.template_records_for_occurrence(
            self._lower_state,
            occurrence_id,
        )
        matches = tuple(
            record
            for record in records
            if record.surface_key == "astichi.surface.elif.production"
        )
        if len(matches) != 1:
            return None
        record_id = RecordId(
            occurrence_id=occurrence_id,
            template_record_id=matches[0].template_record_id,
        )
        return self._lower_engine.locator_for_record(
            self._lower_state,
            record_id,
        ).ast_path

    def _source_funcargs_path(self, occurrence_id: OccurrenceId) -> str | None:
        records = self._lower_engine.template_records_for_occurrence(
            self._lower_state,
            occurrence_id,
        )
        matches = tuple(
            record
            for record in records
            if record.surface_key == "astichi.surface.funcargs.production"
        )
        if len(matches) != 1:
            return None
        record_id = RecordId(
            occurrence_id=occurrence_id,
            template_record_id=matches[0].template_record_id,
        )
        return self._lower_engine.locator_for_record(
            self._lower_state,
            record_id,
        ).ast_path

    def _has_single_block_production(self, occurrence_id: OccurrenceId) -> bool:
        records = self._lower_engine.template_records_for_occurrence(
            self._lower_state,
            occurrence_id,
        )
        return (
            sum(
                1
                for record in records
                if record.surface_key == "astichi.surface.block.production"
            )
            == 1
        )

    def _queue_external_bind(self, owner: str, name: str, value: object) -> None:
        owner_binds = self._pending_external_binds_by_owner.setdefault(owner, {})
        if name in owner_binds:
            raise ValueError(f"external binding `{name}` is already queued")
        owner_binds[name] = value

    def _queue_identifier_bind(self, owner: str, name: str, value: str) -> None:
        owner_binds = self._pending_identifier_binds_by_owner.setdefault(owner, {})
        previous = owner_binds.get(name)
        if previous is not None:
            if previous == value:
                return
            raise ValueError(f"identifier binding `{name}` is already queued")
        owner_binds[name] = value

    def _flush_pending_identifier_binds(self) -> None:
        if not self._pending_identifier_binds_by_owner:
            return
        pending = self._pending_identifier_binds_by_owner
        self._pending_identifier_binds_by_owner = {}
        for owner in sorted(pending):
            composable = self._registered_basic(owner)
            rebound = composable.bind_identifier(pending[owner])
            self.builder.graph.replace_instance(owner, rebound)

    def _flush_pending_external_binds(self) -> None:
        if not self._pending_external_binds_by_owner:
            return
        pending = self._pending_external_binds_by_owner
        self._pending_external_binds_by_owner = {}
        for owner in sorted(pending):
            composable = self._registered_basic(owner)
            rebound = composable.bind(pending[owner])
            self.builder.graph.replace_instance(owner, rebound)

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
            direct = tuple(indexes.by_resource_name.get(selector.name, ()))
            if not self._identifier_bindings_by_occurrence:
                return direct
            return direct + self._resolved_name_record_ids(
                selector.name,
                inventory_kinds=inventory_kinds,
            )
        return tuple(
            record_id
            for kind in inventory_kinds
            for record_id in indexes.by_inventory_kind.get(kind, ())
        )

    def _resolved_name_record_ids(
        self,
        name: str,
        *,
        inventory_kinds: tuple[str, ...],
    ) -> tuple[RecordId, ...]:
        occurrence_ids = tuple(
            occurrence_id
            for occurrence_id, bindings in (
                self._identifier_bindings_by_occurrence.items()
            )
            if name in bindings.values()
        )
        if not occurrence_ids:
            return ()
        occurrence_id_set = frozenset(occurrence_ids)
        matches: list[RecordId] = []
        for kind in inventory_kinds:
            for record_id in self._lower_state.indexes.by_inventory_kind.get(kind, ()):
                if record_id.occurrence_id not in occurrence_id_set:
                    continue
                record = self._lower_projection_by_record_id.get(record_id)
                if record is None:
                    continue
                bindings = self._identifier_bindings_by_occurrence.get(
                    record_id.occurrence_id,
                    {},
                )
                if bindings.get(record.name.logical_name()) == name:
                    matches.append(record_id)
        return tuple(matches)

    def _visible_lower_projection_record(
        self,
        record_id: RecordId,
    ) -> InventoryRecord | None:
        if record_id in self._lower_state.dead_records:
            return None
        if record_id in self._lower_state.satisfied_records:
            return None
        record = self._lower_projection_by_record_id.get(record_id)
        if record is None:
            return None
        return _resolve_projection_record(
            record,
            self._identifier_bindings_by_occurrence.get(
                record_id.occurrence_id,
                {},
            ),
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


def _ast_node_at_path(root: ast.AST, path: str) -> ast.AST:
    node = root
    if path == ".":
        return node
    for part in path.split("/"):
        node = _ast_child(node, part)
    return node


def _replace_ast_node_at_path(root: ast.AST, path: str, replacement: ast.AST) -> None:
    parent_path, _, final_part = path.rpartition("/")
    parent = _ast_node_at_path(root, parent_path) if parent_path else root
    donor = _ast_child(parent, final_part)
    ast.copy_location(replacement, donor)
    field_name, index = _ast_path_part(final_part)
    if index is None:
        setattr(parent, field_name, replacement)
        return
    children = getattr(parent, field_name)
    children[index] = replacement


def _replace_ast_statement_at_path(
    root: ast.AST,
    path: str,
    replacements: list[ast.stmt],
) -> None:
    parent_path, _, final_part = path.rpartition("/")
    parent = _ast_node_at_path(root, parent_path) if parent_path else root
    field_name, index = _ast_path_part(final_part)
    if index is None:
        raise ValueError(f"AST statement path must select a list item: {path}")
    children = getattr(parent, field_name)
    donor = children[index]
    for replacement in replacements:
        ast.copy_location(replacement, donor)
    children[index : index + 1] = replacements


def _ast_child(node: ast.AST, part: str) -> ast.AST:
    field_name, index = _ast_path_part(part)
    value = getattr(node, field_name)
    if index is None:
        if not isinstance(value, ast.AST):
            raise TypeError(f"AST path part does not select a node: {part}")
        return value
    child = value[index]
    if not isinstance(child, ast.AST):
        raise TypeError(f"AST path part does not select a node: {part}")
    return child


def _ast_path_part(part: str) -> tuple[str, int | None]:
    if not part.endswith("]"):
        return part, None
    field_name, _, raw_index = part[:-1].partition("[")
    if not field_name or not raw_index:
        raise ValueError(f"invalid AST path part: {part}")
    return field_name, int(raw_index)


def _statement_path_for_marker_locator(path: str) -> str:
    statement_path, _, _ = path.rpartition("/")
    if not statement_path:
        raise ValueError(f"marker locator does not include a statement path: {path}")
    return statement_path


def _block_statement_path_for_locator(root: ast.AST, path: str) -> str:
    node = _ast_node_at_path(root, path)
    if isinstance(node, ast.stmt):
        return path
    return _statement_path_for_marker_locator(path)


def _if_statement_path_for_elif_locator(path: str) -> str | None:
    statement_path, separator, field_name = path.rpartition("/")
    if not separator or field_name != "test":
        return None
    return statement_path


def _function_path_for_parameter_locator(path: str) -> str | None:
    function_path, separator, _ = path.partition("/args/")
    if not separator or not function_path:
        return None
    return function_path


@dataclass(frozen=True, slots=True)
class _CallArgumentPlacement:
    call_path: str
    index: int
    region_name: str


def _call_argument_placement_for_locator(
    path: str,
    inventory_kind: str,
) -> _CallArgumentPlacement | None:
    if inventory_kind == "hole.positional_variadic":
        call_path, separator, suffix = path.partition("/args[")
        if not separator or not suffix.endswith("]/value"):
            return None
        index_text = suffix.removesuffix("]/value")
        if not index_text.isdigit():
            return None
        return _CallArgumentPlacement(
            call_path=call_path,
            index=int(index_text),
            region_name="starred",
        )
    if inventory_kind == "hole.named_variadic":
        call_path, separator, suffix = path.partition("/keywords[")
        if not separator or not suffix.endswith("]/value"):
            return None
        index_text = suffix.removesuffix("]/value")
        if not index_text.isdigit():
            return None
        return _CallArgumentPlacement(
            call_path=call_path,
            index=int(index_text),
            region_name="dstar",
        )
    return None


def _single_lower_elif_payload_if(node: ast.FunctionDef) -> ast.If | None:
    if node.name != "astichi_elif":
        return None
    payloads = [
        statement
        for statement in node.body
        if not _is_lower_marker_only_statement(statement)
    ]
    if len(payloads) != 1:
        return None
    payload = payloads[0]
    if not isinstance(payload, ast.If):
        return None
    if payload.orelse:
        return None
    return payload


def _is_lower_marker_only_statement(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and (
            _is_lower_boundary_call(statement.value)
            or _is_lower_keep_call(statement.value)
        )
    )


def _body_contains_return(body: Iterable[ast.stmt]) -> bool:
    return any(
        isinstance(node, ast.Return)
        for statement in body
        for node in ast.walk(statement)
    )


def _lower_boundary_available_names(
    root: ast.AST, statement_path: str
) -> frozenset[str]:
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    if not isinstance(root, ast.Module):
        return frozenset()
    scope = root
    node: ast.AST = root
    if statement_path:
        for part in statement_path.split("/"):
            node = _ast_child(node, part)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope = node
    return _lower_scope_binding_names(scope)


def _lower_scope_binding_names(
    scope: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> frozenset[str]:
    names: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for argument in (
            list(scope.args.posonlyargs)
            + list(scope.args.args)
            + list(scope.args.kwonlyargs)
        ):
            names.add(argument.arg)
        if scope.args.vararg is not None:
            names.add(scope.args.vararg.arg)
        if scope.args.kwarg is not None:
            names.add(scope.args.kwarg.arg)

    class _Collector(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            names.add(node.name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            names.add(node.name)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            names.add(node.name)

        def visit_Import(self, node: ast.Import) -> None:
            names.update(import_statement_binding_names(node, include_star=True))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            names.update(import_statement_binding_names(node, include_star=True))

    collector = _Collector()
    for statement in scope.body:
        collector.visit(statement)
    return frozenset(names)


def _lower_boundary_markers_supported(
    source: BasicComposable,
    available_names: frozenset[str],
) -> bool:
    from astichi.lowering.markers import (
        boundary_explicit_bind_enabled,
        boundary_outer_bind_enabled,
    )

    for marker in source.markers:
        if marker.source_name == "astichi_elif":
            continue
        if marker.source_name == "astichi_export":
            continue
        if marker.source_name not in {"astichi_import", "astichi_pass"}:
            return False
        node = marker.node
        if not isinstance(node, ast.Call):
            return False
        name = _lower_boundary_call_name(node)
        if name is None:
            return False
        if (
            boundary_explicit_bind_enabled(node)
            or boundary_outer_bind_enabled(node)
            or name in available_names
        ):
            continue
        return False
    return True


def _strip_lower_boundary_markers(tree: ast.Module) -> None:
    class _Stripper(ast.NodeTransformer):
        def generic_visit(self, node: ast.AST) -> ast.AST:
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    original = tuple(value)
                    new_values: list[object] = []
                    for item in value:
                        if isinstance(item, ast.AST):
                            visited = self.visit(item)
                            if visited is None:
                                continue
                            if isinstance(visited, list):
                                new_values.extend(visited)
                                continue
                            new_values.append(visited)
                            continue
                        new_values.append(item)
                    if (
                        not new_values
                        and any(isinstance(item, ast.stmt) for item in original)
                        and _is_lower_suite_statement_list(node, field)
                    ):
                        new_values.append(ast.Pass())
                    value[:] = new_values
                    continue
                if isinstance(value, ast.AST):
                    visited = self.visit(value)
                    if visited is None:
                        setattr(node, field, None)
                    else:
                        setattr(node, field, visited)
            return node

        def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
            if _is_lower_boundary_call(node.value):
                return None
            return self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> ast.AST:
            replacement = _lower_boundary_replacement(node)
            if replacement is not None:
                return replacement
            return self.generic_visit(node)

    _Stripper().visit(tree)
    ast.fix_missing_locations(tree)


def _strip_lower_keep_markers(tree: ast.Module) -> None:
    from astichi.lowering.markers import strip_identifier_suffix

    class _Stripper(ast.NodeTransformer):
        def generic_visit(self, node: ast.AST) -> ast.AST:
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    original = tuple(value)
                    new_values: list[object] = []
                    for item in value:
                        if isinstance(item, ast.AST):
                            visited = self.visit(item)
                            if visited is None:
                                continue
                            if isinstance(visited, list):
                                new_values.extend(visited)
                                continue
                            new_values.append(visited)
                            continue
                        new_values.append(item)
                    if (
                        not new_values
                        and any(isinstance(item, ast.stmt) for item in original)
                        and _is_lower_suite_statement_list(node, field)
                    ):
                        new_values.append(ast.Pass())
                    value[:] = new_values
                    continue
                if isinstance(value, ast.AST):
                    visited = self.visit(value)
                    if visited is None:
                        setattr(node, field, None)
                    else:
                        setattr(node, field, visited)
            return node

        def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
            if _is_lower_keep_call(node.value):
                return None
            return self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> ast.AST:
            if _is_lower_keep_call(node):
                replacement = _lower_keep_replacement(node)
                if replacement is not None:
                    return replacement
            return self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> ast.AST:
            stripped, marker = strip_identifier_suffix(node.id)
            if marker is not None and marker.source_name == "astichi_keep_identifier":
                node.id = stripped
            return node

        def visit_arg(self, node: ast.arg) -> ast.AST:
            stripped, marker = strip_identifier_suffix(node.arg)
            if marker is not None and marker.source_name == "astichi_keep_identifier":
                node.arg = stripped
            return node

        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            stripped, marker = strip_identifier_suffix(node.name)
            if marker is not None and marker.source_name == "astichi_keep_identifier":
                node.name = stripped
            return self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
            stripped, marker = strip_identifier_suffix(node.name)
            if marker is not None and marker.source_name == "astichi_keep_identifier":
                node.name = stripped
            return self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
            stripped, marker = strip_identifier_suffix(node.name)
            if marker is not None and marker.source_name == "astichi_keep_identifier":
                node.name = stripped
            return self.generic_visit(node)

    _Stripper().visit(tree)
    ast.fix_missing_locations(tree)


def _lower_keep_replacement(node: ast.Call) -> ast.expr | None:
    if len(node.args) != 1 or node.keywords:
        return None
    replacement = clone_ast(node.args[0])
    ast.copy_location(replacement, node)
    return replacement


def _is_lower_keep_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "astichi_keep"
    )


def _lower_boundary_replacement(node: ast.Call) -> ast.expr | None:
    name = _lower_boundary_call_name(node)
    if name is None:
        return None
    replacement = ast.Name(id=name, ctx=ast.Load())
    ast.copy_location(replacement, node)
    return replacement


def _lower_boundary_call_name(node: ast.Call) -> str | None:
    if not _is_lower_boundary_call(node):
        return None
    if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
        return None
    return node.args[0].id


def _is_lower_boundary_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"astichi_export", "astichi_import", "astichi_pass"}
    )


def _is_lower_suite_statement_list(node: ast.AST, field: str) -> bool:
    if isinstance(node, ast.Module):
        return False
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return field == "body"
    if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While)):
        return field in {"body", "orelse"}
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return field == "body"
    return False


def _fresh_lower_scoped_name(
    name: str,
    unavailable: set[str],
    counter: int,
) -> tuple[str, int]:
    while True:
        candidate = f"{name}__astichi_scoped_{counter}"
        counter += 1
        if candidate not in unavailable:
            return candidate, counter


def _rename_lower_names(body: list[ast.stmt], rename_map: dict[str, str]) -> None:
    class _Renamer(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.AST:
            replacement = rename_map.get(node.id)
            if replacement is not None:
                node.id = replacement
            return node

        def visit_arg(self, node: ast.arg) -> ast.AST:
            replacement = rename_map.get(node.arg)
            if replacement is not None:
                node.arg = replacement
            return node

        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            replacement = rename_map.get(node.name)
            if replacement is not None:
                node.name = replacement
            return self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
            replacement = rename_map.get(node.name)
            if replacement is not None:
                node.name = replacement
            return self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
            replacement = rename_map.get(node.name)
            if replacement is not None:
                node.name = replacement
            return self.generic_visit(node)

    renamer = _Renamer()
    for statement in body:
        renamer.visit(statement)


def _module_pyimport_call_ids(tree: ast.Module) -> frozenset[int]:
    call_ids: set[int] = set()
    for statement in tree.body:
        if not isinstance(statement, ast.Expr):
            continue
        if _is_lower_pyimport_call(statement.value):
            call_ids.add(id(statement.value))
    return frozenset(call_ids)


def _lower_pyimport_collides_with_existing_bindings(
    tree: ast.Module,
    records: Iterable[object],
) -> bool:
    final_names = tuple(
        name
        for record in records
        if isinstance((name := getattr(record, "final_local_name", None)), str)
    )
    if len(final_names) != len(set(final_names)):
        return True
    bindings: set[str] = set()

    class _BindingCollector(ast.NodeVisitor):
        def visit_Expr(self, node: ast.Expr) -> None:
            if _is_lower_pyimport_call(node.value):
                return
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                bindings.add(node.id)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            bindings.add(node.name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            bindings.add(node.name)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            bindings.add(node.name)

        def visit_Import(self, node: ast.Import) -> None:
            bindings.update(import_statement_binding_names(node, include_star=True))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            bindings.update(import_statement_binding_names(node, include_star=True))

    _BindingCollector().visit(tree)
    return bool(set(final_names) & bindings)


def _strip_lower_pyimport_declarations(tree: ast.Module) -> None:
    class _Stripper(ast.NodeTransformer):
        def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
            if _is_lower_pyimport_call(node.value):
                return None
            return self.generic_visit(node)

    _Stripper().visit(tree)
    ast.fix_missing_locations(tree)


def _is_lower_pyimport_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "astichi_pyimport"
    )


def _has_unresolved_lower_astichi_demands(composable: BasicComposable) -> bool:
    return any(
        port.is_additive_hole_demand()
        or port.is_external_bind_demand()
        or port.is_identifier_demand()
        or port.is_parameter_hole_demand()
        for port in composable.demand_ports
    )


def _ordered_unique_operation_targets(
    operations: list[MaterializationOperation],
) -> tuple[RecordId, ...]:
    targets: list[RecordId] = []
    seen: set[RecordId] = set()
    for operation in operations:
        target = operation.target_record_id
        if target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return tuple(targets)


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
    build_prefix: tuple[str, ...],
    spec: TemplateRecordSpec,
) -> InventoryRecord | None:
    record = spec.projection_record
    if not isinstance(record, InventoryRecord):
        return None
    return InventoryRecord(
        record_id=_prefix_inventory_record_id(build_prefix, record.record_id),
        build_path=record.build_path.prefixed(ResourcePath(build_prefix)),
        code_owner=record.code_owner,
        name=record.name,
        kind=record.kind,
        locator=record.locator,
        payload=record.payload,
        source_location=record.source_location,
    )


def _resolve_projection_record(
    record: InventoryRecord,
    identifier_bindings: dict[str, str],
) -> InventoryRecord:
    if not identifier_bindings:
        return record
    name = record.name.logical_name()
    resolved_name = identifier_bindings.get(name, name)
    code_owner = _resolve_code_owner(record.code_owner, identifier_bindings)
    if resolved_name == name and code_owner == record.code_owner:
        return record
    return InventoryRecord(
        record_id=record.record_id,
        build_path=record.build_path,
        code_owner=code_owner,
        name=(
            record.name if resolved_name == name else StaticResourceName(resolved_name)
        ),
        kind=record.kind,
        locator=record.locator,
        payload=record.payload,
        source_location=record.source_location,
    )


def _resolve_code_owner(
    code_owner: CodePath,
    identifier_bindings: dict[str, str],
) -> CodePath:
    nodes: list[CodePathNode] = []
    changed = False
    for node in code_owner.nodes:
        name = node.logical_name()
        resolved_name = identifier_bindings.get(name, name)
        if resolved_name == name:
            nodes.append(node)
            continue
        changed = True
        nodes.append(
            _ResolvedCodePathNode(
                name=resolved_name,
                source_location=_code_owner_location(node),
            )
        )
    if not changed:
        return code_owner
    return CodePath(tuple(nodes))


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
            record_id for ids in record_map.values() for record_id in ids
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
        record_id for ids in inventory.production_map.values() for record_id in ids
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
    if isinstance(node, _ResolvedCodePathNode):
        return node.source_location
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
