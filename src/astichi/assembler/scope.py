"""Inventory-driven assembly scope helpers."""

from __future__ import annotations

import ast
import os
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
    NativeTemplateCache,
    TemplateRecordSpec,
    load_native_extension,
    select_effective_lower_engine,
    select_lower_engine,
)
from astichi.lower_engine.handles import (
    OccurrenceId,
    OverlayId,
    RecordId,
    TemplateRecordId,
)
from astichi.lower_engine.inventory import AssemblyState
from astichi.lower_engine.materialization import MaterializationOperation
from astichi.lowering.parameters import param_hole_name
from astichi.lowering.markers import (
    ARG_IDENTIFIER,
    BIND_EXTERNAL,
    ELIF,
    EXPORT,
    HOLE,
    IMPORT,
    KEEP,
    PARAM_HOLE_IDENTIFIER,
    PASS,
    PYIMPORT,
    strip_identifier_suffix,
)
from astichi.lowering.sentinel_attrs import match_transparent_sentinel
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
    LocatedStaticCodePathNode,
    MutableInventory,
    PortDescriptor,
    PortInventoryPayload,
    ProductionDescriptor,
    ResourcePath,
    SourceLocation,
    StaticResourceName,
    empty_inventory,
    external_value_to_source,
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

_UNRESOLVED_LOWER_CALL_DEMANDS = frozenset(
    (
        HOLE.source_name,
        ELIF.source_name,
        BIND_EXTERNAL.source_name,
        IMPORT.source_name,
        PASS.source_name,
        KEEP.source_name,
        EXPORT.source_name,
        PYIMPORT.source_name,
    )
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
class BindingRequest:
    """One resource-resolution request for batched scope application."""

    resource: BindingResource
    name: str | None = None
    build_match: tuple[str, ...] | None = None
    owner_match: tuple[str, ...] | None = None
    allow_equivalent_demand_sites: bool = False


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
    _deferred_composable_adapter_edges: list[ComposableCandidate] = field(
        default_factory=list,
        init=False,
    )
    _native_module: object | None = field(default=None, init=False)
    _native_engine_handle: object | None = field(default=None, init=False)
    _native_template_cache: NativeTemplateCache | None = field(
        default=None,
        init=False,
    )
    _native_state_handle: object | None = field(default=None, init=False)
    _native_occurrence_by_build_prefix: dict[tuple[str, ...], object] = field(
        default_factory=dict,
        init=False,
    )

    def __post_init__(self) -> None:
        self._lower_cache = LowerTemplateCache(self._lower_engine)
        self._lower_state = self._lower_engine.new_state()
        self._initialize_native_scope_backend()
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

    def native_lower_structural_snapshot(self) -> dict[str, object]:
        """Return the explicit-native scope structural state."""
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            raise RuntimeError("native scope backend is not enabled")
        snapshot = self._native_module.assembly_state_snapshot(
            self._native_engine_handle,
            self._native_state_handle,
        )
        if not isinstance(snapshot, dict):
            raise TypeError("native scope structural snapshot must be a dict")
        return snapshot

    def native_lower_materialization_snapshot(self) -> dict[str, object]:
        """Return the explicit-native materialization-plan snapshot."""
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            raise RuntimeError("native scope backend is not enabled")
        snapshot = self._native_module.assembly_state_materialization_plan_snapshot(
            self._native_engine_handle,
            self._native_state_handle,
            None,
        )
        if not isinstance(snapshot, dict):
            raise TypeError("native materialization snapshot must be a dict")
        return snapshot

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
        return self._find_candidates(resource, selector)

    def apply_batch(
        self,
        requests: Iterable[BindingRequest],
    ) -> tuple[BindingCandidate, ...]:
        """Resolve and apply a sequence of binding requests through the lower layer."""
        request_tuple = tuple(requests)
        counters = active_perf_counters()
        counter_prefix = (
            "native_scope_batch"
            if self._native_module is not None
            else "scope_batch"
        )
        if counters is None:
            return self._apply_batch_uncounted(request_tuple)
        with counters.measure(counter_prefix):
            counters.increment(f"{counter_prefix}_size", len(request_tuple))
            candidates = self._apply_batch_uncounted(request_tuple)
            counters.increment(f"{counter_prefix}_apply_count", len(candidates))
            return candidates

    def _apply_batch_uncounted(
        self,
        requests: tuple[BindingRequest, ...],
    ) -> tuple[BindingCandidate, ...]:
        native_candidates = self._try_apply_native_batch(requests)
        if native_candidates is not None:
            return native_candidates
        applied: list[BindingCandidate] = []
        candidate_count = 0
        for request in requests:
            try:
                candidates = self._find_candidates(
                    request.resource,
                    DemandSelector(
                        name=request.name,
                        build_match=request.build_match,
                        owner_match=request.owner_match,
                    ),
                )
                candidate_count += len(candidates)
                candidate = _select_batch_candidate(
                    candidates,
                    allow_equivalent_demand_sites=(
                        request.allow_equivalent_demand_sites
                    ),
                )
                self._apply_candidate(candidate, count_compatibility_kind=False)
            except ValueError as exc:
                label = (
                    f" {request.name!r}"
                    if request.name is not None
                    else f" for {type(request.resource).__name__}"
                )
                raise ValueError(f"failed to apply binding request{label}") from exc
            applied.append(candidate)
        counters = active_perf_counters()
        if counters is not None:
            counter_prefix = (
                "native_scope_batch"
                if self._native_module is not None
                else "scope_batch"
            )
            counters.increment(f"{counter_prefix}_candidate_count", candidate_count)
        return tuple(applied)

    def _try_apply_native_batch(
        self,
        requests: tuple[BindingRequest, ...],
    ) -> tuple[BindingCandidate, ...] | None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_template_cache is None
            or self._native_state_handle is None
        ):
            return None
        native_requests = self._native_batch_request_payload(requests)
        if native_requests is None:
            return None
        result = self._native_module.assembly_state_apply_request_batch(
            self._native_engine_handle,
            self._native_state_handle,
            native_requests,
        )
        if not isinstance(result, dict):
            raise TypeError("native batch result must be a dict")
        raw_events = result.get("events")
        if not isinstance(raw_events, list):
            raise TypeError("native batch result events must be a list")
        summary = result.get("diagnostic_summary", {})
        candidate_count = (
            summary.get("candidate_count", 0) if isinstance(summary, dict) else 0
        )
        counters = active_perf_counters()
        if counters is not None:
            counters.increment("native_scope_batch_engine")
            counters.increment("native_scope_batch_engine_request_count", len(requests))
            counters.increment(
                "native_scope_batch_engine_candidate_count",
                int(candidate_count),
            )
            counters.increment("native_scope_batch_candidate_count", int(candidate_count))
        if len(raw_events) != len(requests):
            return None
        if _native_scope_mirror_replay_enabled():
            candidates = self._replay_native_batch_events(requests, raw_events)
            if counters is not None:
                counters.increment("python_scope_mirror_replay", len(candidates))
            return candidates
        self._commit_native_batch_without_mirror_replay(requests, raw_events)
        if counters is not None:
            counters.increment("native_scope_batch_native_only", len(raw_events))
        return ()

    def _native_batch_request_payload(
        self,
        requests: tuple[BindingRequest, ...],
    ) -> list[dict[str, object]] | None:
        payload: list[dict[str, object]] = []
        for index, request in enumerate(requests):
            selector_payload: dict[str, object] = {
                "name": request.name,
                "build_match": (
                    None
                    if request.build_match is None
                    else list(request.build_match)
                ),
                "owner_match": (
                    None
                    if request.owner_match is None
                    else list(request.owner_match)
                ),
                "allow_equivalent_demand_sites": (
                    request.allow_equivalent_demand_sites
                ),
            }
            resource = request.resource
            if isinstance(resource, ComposableResource):
                native = self._native_composable_batch_payload(resource, request)
                if native is None:
                    return None
                payload.append({**selector_payload, **native})
                continue
            if isinstance(resource, ExternalValueResource):
                payload.append(
                    {
                        **selector_payload,
                        "resource_kind": "external",
                        "value_token": index,
                    }
                )
                continue
            if isinstance(resource, IdentifierNameResource):
                payload.append(
                    {
                        **selector_payload,
                        "resource_kind": "identifier",
                        "identifier": resource.identifier,
                    }
                )
                continue
            return None
        return payload

    def _native_composable_batch_payload(
        self,
        resource: ComposableResource,
        request: BindingRequest,
    ) -> dict[str, object] | None:
        if not isinstance(resource.composable, BasicComposable):
            return None
        binding = resource.composable._lower_template
        if not isinstance(binding, LowerTemplateBinding):
            return None
        if binding.native_snapshot is None and (
            binding.native_source is None or binding.native_origin is None
        ):
            return None
        template_handle = self._native_template_cache.template_handle_for(binding)
        return {
            "resource_kind": "composable",
            "source_template": template_handle,
            "source_instance_name": resource.instance_name,
            "operation_order": resource.order,
        }

    def _native_overlay_id(self, overlay_index: int) -> OverlayId:
        """Map native overlay indices to lower-engine overlay handles for materialization."""
        if not self._lower_state.occurrences:
            raise RuntimeError("lower state has no occurrences for native overlay id")
        owner = self._lower_state.occurrences[0].occurrence_id.owner
        return OverlayId(owner=owner, index=overlay_index)

    def _commit_native_batch_without_mirror_replay(
        self,
        requests: tuple[BindingRequest, ...],
        events: list[object],
    ) -> None:
        """Keep native-owned state authoritative without mirroring into Python lower state."""
        for event in events:
            if not isinstance(event, dict):
                raise TypeError("native batch event entries must be dicts")
            request_index = event.get("request_index")
            if not isinstance(request_index, int):
                raise TypeError("native batch event request_index must be an int")
            try:
                request = requests[request_index]
            except IndexError as exc:
                raise RuntimeError(
                    f"native batch event references unknown request {request_index}"
                ) from exc
            kind = event.get("kind")
            if kind == "composable":
                resource = request.resource
                if not isinstance(resource, ComposableResource):
                    raise TypeError("native composable event does not match request")
                source_build_prefix = _string_tuple_field(event, "source_build_path")
                native_occurrence = event.get("source_occurrence_handle")
                if native_occurrence is None:
                    raise RuntimeError(
                        "native batch composable event is missing occurrence handle"
                    )
                self._native_occurrence_by_build_prefix[source_build_prefix] = (
                    native_occurrence
                )
                self._owner_by_build_prefix[source_build_prefix] = resource.instance_name
                continue
            if kind == "external":
                resource = request.resource
                if not isinstance(resource, ExternalValueResource):
                    raise TypeError("native external event does not match request")
                overlay_index = event.get("overlay_id")
                if not isinstance(overlay_index, int):
                    raise TypeError("native batch overlay_id must be an int")
                self._external_value_by_overlay[
                    self._native_overlay_id(overlay_index)
                ] = resource.value
                continue
            if kind == "identifier":
                resource = request.resource
                if not isinstance(resource, IdentifierNameResource):
                    raise TypeError("native identifier event does not match request")
                overlay_index = event.get("overlay_id")
                if not isinstance(overlay_index, int):
                    raise TypeError("native batch overlay_id must be an int")
                overlay_id = self._native_overlay_id(overlay_index)
                self._identifier_value_by_overlay[overlay_id] = resource.identifier
                continue
            raise TypeError(f"unsupported native batch event kind: {kind!r}")

    def _replay_native_batch_events(
        self,
        requests: tuple[BindingRequest, ...],
        events: list[object],
    ) -> tuple[BindingCandidate, ...]:
        candidates: list[BindingCandidate] = []
        if len(events) != len(requests):
            raise RuntimeError(
                "native batch event count does not match request count"
            )
        for event in events:
            if not isinstance(event, dict):
                raise TypeError("native batch event entries must be dicts")
            request_index = event.get("request_index")
            if not isinstance(request_index, int):
                raise TypeError("native batch event request_index must be an int")
            try:
                request = requests[request_index]
            except IndexError as exc:
                raise RuntimeError(
                    f"native batch event references unknown request {request_index}"
                ) from exc
            candidate = self._replay_native_batch_event(request, event)
            candidates.append(candidate)
        return tuple(candidates)

    def _replay_native_batch_event(
        self,
        request: BindingRequest,
        event: dict[str, object],
    ) -> BindingCandidate:
        kind = event.get("kind")
        target_record = self._native_batch_target_record(event)
        if kind == "composable":
            resource = request.resource
            if not isinstance(resource, ComposableResource):
                raise TypeError("native composable event does not match request")
            candidate = ComposableCandidate(
                target_record=target_record,
                resource=resource,
                compatible_productions=self._native_batch_production_records(
                    resource,
                    event,
                ),
            )
            self._replay_native_composable_event(candidate, event)
            return candidate
        if kind == "external":
            resource = request.resource
            if not isinstance(resource, ExternalValueResource):
                raise TypeError("native external event does not match request")
            candidate = ExternalValueCandidate(
                demand_record=target_record,
                resource=resource,
            )
            self._replay_native_external_event(candidate, event)
            return candidate
        if kind == "identifier":
            resource = request.resource
            if not isinstance(resource, IdentifierNameResource):
                raise TypeError("native identifier event does not match request")
            candidate = IdentifierNameCandidate(
                demand_record=target_record,
                resource=resource,
            )
            self._replay_native_identifier_event(candidate, event)
            return candidate
        raise TypeError(f"unsupported native batch event kind: {kind!r}")

    def _native_batch_target_record(
        self,
        event: dict[str, object],
    ) -> InventoryRecord:
        target_record_id = self._native_record_id(event.get("target_record"))
        record = self._visible_lower_projection_record(target_record_id)
        if record is None:
            raise RuntimeError(
                f"native batch selected non-visible record {target_record_id}"
            )
        return record

    def _native_batch_production_records(
        self,
        resource: ComposableResource,
        event: dict[str, object],
    ) -> tuple[InventoryRecord, ...]:
        if not isinstance(resource.composable, BasicComposable):
            raise TypeError("native composable batch requires BasicComposable")
        production_records = _lower_template_projection_production_records(
            resource.composable
        )
        records: list[InventoryRecord] = []
        for index in _native_template_record_indexes(event.get("production_records")):
            record = production_records.get(index)
            if record is None:
                raise TypeError(
                    "native batch references a non-production template record"
                )
            records.append(record)
        return tuple(records)

    def _replay_native_composable_event(
        self,
        candidate: ComposableCandidate,
        event: dict[str, object],
    ) -> None:
        resource = candidate.resource
        source_build_prefix = _string_tuple_field(event, "source_build_path")
        self._owner_by_build_prefix[source_build_prefix] = resource.instance_name
        self._deferred_composable_adapter_edges.append(candidate)
        target_record_id = self._lower_record_by_inventory_id.get(
            candidate.target_record.record_id
        )
        if target_record_id is None:
            raise RuntimeError("native batch target record is missing lower mirror")
        if bool(event.get("mark_satisfied")):
            self._mark_record_satisfied(candidate.target_record.record_id)
            self._lower_engine.mark_satisfied(self._lower_state, target_record_id)
        source_occurrence = self._append_lower_occurrence(
            source_build_prefix,
            resource.composable,
            parent_occurrence_id=target_record_id.occurrence_id,
            append_native=False,
        )
        native_occurrence = event.get("source_occurrence_handle")
        if native_occurrence is None:
            raise RuntimeError("native batch composable event is missing occurrence")
        self._native_occurrence_by_build_prefix[source_build_prefix] = native_occurrence
        operation_key = event.get("operation_key")
        if not isinstance(operation_key, str):
            raise TypeError("native batch operation_key must be a string")
        order = event.get("order")
        if not isinstance(order, int):
            raise TypeError("native batch order must be an int")
        self._lower_engine.append_edge(
            self._lower_state,
            target_record_id=target_record_id,
            source_occurrence_id=source_occurrence,
            operation_key=operation_key,
            order=order,
        )

    def _replay_native_external_event(
        self,
        candidate: ExternalValueCandidate,
        event: dict[str, object],
    ) -> None:
        record_id, overlay_id = self._append_lower_overlay_only(
            candidate.demand_record,
            kind="external",
            source_label=_string_field(event, "source_label"),
        )
        self._external_value_by_overlay[overlay_id] = candidate.resource.value
        owner = self._owner_for(candidate.demand_record)
        self._queue_external_bind(
            owner,
            candidate.demand_record.name.logical_name(),
            candidate.resource.value,
        )
        _assert_native_overlay_alignment(event, overlay_id.index)
        _ = record_id

    def _replay_native_identifier_event(
        self,
        candidate: IdentifierNameCandidate,
        event: dict[str, object],
    ) -> None:
        record_id, overlay_id = self._append_lower_overlay_only(
            candidate.demand_record,
            kind="identifier",
            source_label=_string_field(event, "source_label"),
        )
        self._identifier_value_by_overlay[overlay_id] = candidate.resource.identifier
        authored_name = candidate.demand_record.name.logical_name()
        self._identifier_bindings_by_occurrence.setdefault(
            record_id.occurrence_id,
            {},
        )[authored_name] = candidate.resource.identifier
        owner = self._owner_for(candidate.demand_record)
        self._queue_identifier_bind(
            owner,
            authored_name,
            candidate.resource.identifier,
        )
        _assert_native_overlay_alignment(event, overlay_id.index)

    def _find_candidates(
        self,
        resource: BindingResource,
        selector: DemandSelector,
    ) -> tuple[BindingCandidate, ...]:
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
        self._apply_candidate(candidate, count_compatibility_kind=True)

    def _apply_candidate(
        self,
        candidate: BindingCandidate,
        *,
        count_compatibility_kind: bool,
    ) -> None:
        counters = active_perf_counters()
        if isinstance(candidate, ComposableCandidate):
            if counters is not None and count_compatibility_kind:
                counters.increment("assembly_scope_apply_composable")
            self._apply_composable(candidate)
            return
        if isinstance(candidate, ExternalValueCandidate):
            if counters is not None and count_compatibility_kind:
                counters.increment("assembly_scope_apply_external_value")
            self._apply_external_value(candidate)
            return
        if isinstance(candidate, IdentifierNameCandidate):
            if counters is not None and count_compatibility_kind:
                counters.increment("assembly_scope_apply_identifier_name")
            self._apply_identifier_name(candidate)
            return
        raise TypeError(f"unsupported binding candidate: {type(candidate).__name__}")

    def _reject_python_materialize_fallback(self, operation: str) -> None:
        from astichi.lower_engine.self_native_gates import (
            native_materialize_no_python_fallback_enabled,
        )

        if not native_materialize_no_python_fallback_enabled():
            return
        if select_effective_lower_engine().selected_engine == "python":
            return
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            return
        raise RuntimeError(
            f"{operation} requires native materialization but the native "
            "materializer did not produce a composable"
        )

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
        if unroll in ("auto", False):
            self._reject_python_materialize_fallback("scope.build")
        if counters is not None:
            counters.increment("lower_materialization_adapter_fallback")
        return self._build_with_adapter(unroll=unroll)

    def _build_with_adapter(self, *, unroll: bool | str = "auto") -> BasicComposable:
        self._flush_deferred_composable_adapter_edges()
        self._flush_pending_identifier_binds()
        self._flush_pending_external_binds()
        return self.builder.build(unroll=unroll)

    @counted_perf_call("lower_materialize")
    def lower_materialize(self) -> BasicComposable:
        """Materialize the currently supported lower-owned subset."""
        materialized = self._lower_materialize_if_supported()
        counters = active_perf_counters()
        if materialized is None:
            self._reject_python_materialize_fallback("scope.lower_materialize")
            if counters is not None:
                counters.increment("lower_materialization_adapter_fallback")
            return self._build_with_adapter().materialize()
        if counters is not None:
            counters.increment("lower_materialization_artifact")
        return materialized

    def _apply_composable(self, candidate: ComposableCandidate) -> None:
        resource = candidate.resource
        build_path = candidate.target_record.build_path.parts
        if not build_path:
            raise ValueError("target hole record must have a non-empty build path")
        self._owner_by_build_prefix[build_path + (resource.instance_name,)] = (
            resource.instance_name
        )
        self._deferred_composable_adapter_edges.append(candidate)
        if _record_is_single_additive_hole_demand(candidate.target_record):
            self._mark_record_satisfied(candidate.target_record.record_id)
            self._mark_lower_record_satisfied(candidate.target_record.record_id)
        target_lower_record = self._lower_record_by_inventory_id.get(
            candidate.target_record.record_id
        )
        source_build_prefix = build_path + (resource.instance_name,)
        source_occurrence = self._append_lower_occurrence(
            source_build_prefix,
            resource.composable,
            parent_occurrence_id=self._lower_occurrence_by_build_prefix.get(build_path),
        )
        if target_lower_record is not None:
            operation_key = _operation_key_for_target(candidate.target_record)
            self._lower_engine.append_edge(
                self._lower_state,
                target_record_id=target_lower_record,
                source_occurrence_id=source_occurrence,
                operation_key=operation_key,
                order=resource.order,
            )
            self._append_native_composable_edge(
                target_lower_record,
                source_build_prefix=source_build_prefix,
                operation_key=operation_key,
                order=resource.order,
            )

    def _flush_deferred_composable_adapter_edges(self) -> None:
        if not self._deferred_composable_adapter_edges:
            return
        counters = active_perf_counters()
        deferred = self._deferred_composable_adapter_edges
        self._deferred_composable_adapter_edges = []
        for candidate in deferred:
            if counters is not None:
                counters.increment("builder_adapter_mutation")
            self._apply_composable_to_builder_adapter(candidate)

    def _apply_composable_to_builder_adapter(
        self,
        candidate: ComposableCandidate,
    ) -> None:
        resource = candidate.resource
        self.builder.add(
            resource.build_name,
            resource.composable,
            indexes=resource.build_index,
        )
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

    def _initialize_native_scope_backend(self) -> None:
        selected = select_effective_lower_engine().selected_engine
        if selected not in {"native-rust", "native-cpp"}:
            return
        module = load_native_extension(required=True)
        assert module is not None
        engine_handle = module.engine_create()
        self._native_module = module
        self._native_engine_handle = engine_handle
        self._native_template_cache = NativeTemplateCache(
            module=module,
            engine_handle=engine_handle,
        )
        self._native_state_handle = module.assembly_state_create(engine_handle)

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
        append_native: bool = True,
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
        if append_native:
            self._append_native_occurrence(
                build_prefix,
                binding,
                parent_occurrence_id=parent_occurrence_id,
            )
        return occurrence_id

    def _append_native_occurrence(
        self,
        build_prefix: tuple[str, ...],
        binding: LowerTemplateBinding,
        *,
        parent_occurrence_id: OccurrenceId | None,
    ) -> object | None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_template_cache is None
            or self._native_state_handle is None
        ):
            return None
        if binding.native_snapshot is None and (
            binding.native_source is None or binding.native_origin is None
        ):
            raise TypeError(
                "explicit native scope add requires native template metadata"
            )
        template_handle = self._native_template_cache.template_handle_for(binding)
        parent_native_occurrence = None
        if parent_occurrence_id is not None:
            parent_build_prefix = build_prefix[:-1]
            parent_native_occurrence = self._native_occurrence_by_build_prefix.get(
                parent_build_prefix
            )
            if parent_native_occurrence is None:
                raise RuntimeError(
                    "native parent occurrence is missing for build path "
                    f"{parent_build_prefix!r}"
                )
        occurrence = self._native_module.assembly_state_append_occurrence(
            self._native_engine_handle,
            self._native_state_handle,
            template_handle,
            build_prefix,
            parent_native_occurrence,
        )
        self._native_occurrence_by_build_prefix[build_prefix] = occurrence
        counters = active_perf_counters()
        if counters is not None:
            counters.increment("native_scope_append_occurrence")
        return occurrence

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
            self._mark_native_record_satisfied(record_id)

    def _native_record_handle_for(self, record_id: RecordId) -> object | None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            return None
        occurrence = self._lower_state.occurrences[record_id.occurrence_id.index]
        native_occurrence = self._native_occurrence_by_build_prefix.get(
            occurrence.build_path
        )
        if native_occurrence is None:
            raise RuntimeError(
                "native occurrence is missing for build path "
                f"{occurrence.build_path!r}"
            )
        return self._native_module.assembly_state_record_handle(
            self._native_engine_handle,
            self._native_state_handle,
            native_occurrence,
            record_id.template_record_id.index,
        )

    def _mark_native_record_satisfied(self, record_id: RecordId) -> None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            return
        record_handle = self._native_record_handle_for(record_id)
        assert record_handle is not None
        self._native_module.assembly_state_mark_satisfied(
            self._native_engine_handle,
            self._native_state_handle,
            record_handle,
        )
        counters = active_perf_counters()
        if counters is not None:
            counters.increment("native_scope_mark_satisfied")

    def _append_native_composable_edge(
        self,
        target_record_id: RecordId,
        *,
        source_build_prefix: tuple[str, ...],
        operation_key: str,
        order: int,
    ) -> object | None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            return None
        target_record = self._native_record_handle_for(target_record_id)
        source_occurrence = self._native_occurrence_by_build_prefix.get(
            source_build_prefix
        )
        if source_occurrence is None:
            raise RuntimeError(
                "native source occurrence is missing for build path "
                f"{source_build_prefix!r}"
            )
        edge = self._native_module.assembly_state_append_edge(
            self._native_engine_handle,
            self._native_state_handle,
            target_record,
            source_occurrence,
            operation_key,
            order,
        )
        counters = active_perf_counters()
        if counters is not None:
            counters.increment("native_scope_append_edge")
        return edge

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
        if kind in {"external", "identifier"}:
            self._append_native_overlay(
                record_id,
                kind=kind,
                source_label=source_label,
            )
            self._mark_native_record_satisfied(record_id)
        return record_id, overlay_id

    def _append_lower_overlay_only(
        self,
        demand_record: InventoryRecord,
        *,
        kind: str,
        source_label: str,
    ) -> tuple[RecordId, OverlayId]:
        record_id = self._lower_record_by_inventory_id.get(demand_record.record_id)
        if record_id is None:
            raise RuntimeError("overlay target record is missing lower mirror")
        overlay_id = self._lower_engine.append_overlay(
            self._lower_state,
            kind=kind,
            source_label=source_label,
            target_record_id=record_id,
        )
        self._lower_engine.mark_satisfied(self._lower_state, record_id)
        return record_id, overlay_id

    def _append_native_overlay(
        self,
        target_record_id: RecordId,
        *,
        kind: str,
        source_label: str,
    ) -> object | None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            return None
        target_record = self._native_record_handle_for(target_record_id)
        overlay = self._native_module.assembly_state_append_overlay(
            self._native_engine_handle,
            self._native_state_handle,
            target_record,
            kind,
            source_label,
        )
        counters = active_perf_counters()
        if counters is not None:
            counters.increment("native_scope_append_overlay")
        return overlay

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
        operations_by_occurrence = _operations_by_target_occurrence(plan)
        tree = self._materialize_lower_occurrence_tree(
            root_id,
            operations_by_occurrence,
            cache={},
            visiting=set(),
        )
        if tree is None:
            return None
        ast.fix_missing_locations(tree)
        if _tree_has_unresolved_lower_astichi_demands(tree):
            return None
        return BasicComposable(
            tree=tree,
            origin=root.origin,
            bound_externals=frozenset(),
            _already_materialized=True,
        )

    def _materialize_lower_occurrence_tree(
        self,
        occurrence_id: OccurrenceId,
        operations_by_occurrence: dict[
            OccurrenceId, tuple[MaterializationOperation, ...]
        ],
        *,
        cache: dict[OccurrenceId, ast.Module],
        visiting: set[OccurrenceId],
    ) -> ast.Module | None:
        cached = cache.get(occurrence_id)
        if cached is not None:
            return cached
        if occurrence_id in visiting:
            return None
        occurrence = self._lower_engine.occurrence(self._lower_state, occurrence_id)
        if not occurrence.live:
            return None
        root = self._lower_composable_by_occurrence.get(occurrence_id)
        if root is None:
            return None
        visiting.add(occurrence_id)
        tree = clone_ast(root.tree)
        operations = operations_by_occurrence.get(occurrence_id, ())
        source_trees: dict[OccurrenceId, ast.Module] = {}
        for operation in operations:
            source_id = operation.source_occurrence_id
            if source_id is None or source_id in source_trees:
                continue
            source_tree = self._materialize_lower_occurrence_tree(
                source_id,
                operations_by_occurrence,
                cache=cache,
                visiting=visiting,
            )
            if source_tree is None:
                visiting.remove(occurrence_id)
                return None
            source_trees[source_id] = source_tree
        if not self._apply_lower_operations_to_tree(
            tree,
            occurrence_id,
            operations,
            source_trees=source_trees,
        ):
            visiting.remove(occurrence_id)
            return None
        _strip_lower_boundary_markers(tree)
        _strip_lower_keep_markers(tree)
        if not self._apply_lower_managed_pyimports(tree):
            visiting.remove(occurrence_id)
            return None
        ast.fix_missing_locations(tree)
        cache[occurrence_id] = tree
        visiting.remove(occurrence_id)
        return tree

    def _apply_lower_operations_to_tree(
        self,
        tree: ast.Module,
        occurrence_id: OccurrenceId,
        operations: tuple[MaterializationOperation, ...],
        *,
        source_trees: dict[OccurrenceId, ast.Module],
    ) -> bool:
        identifier_bindings: dict[str, str] = {}
        external_bindings: dict[str, object] = {}
        expression_operations: list[MaterializationOperation] = []
        block_operations: list[MaterializationOperation] = []
        parameter_operations: list[MaterializationOperation] = []
        elif_operations: list[MaterializationOperation] = []
        call_argument_operations: list[MaterializationOperation] = []
        for operation in operations:
            if operation.target_record_id.occurrence_id != occurrence_id:
                return False
            if operation.operation_key == "astichi.operation.rewrite_identifier":
                if not self._collect_identifier_operation(
                    operation,
                    identifier_bindings,
                ):
                    return False
                continue
            if operation.operation_key == "astichi.operation.lower_external_ref":
                if not self._collect_external_operation(
                    operation,
                    external_bindings,
                ):
                    return False
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
            return False

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
            if not self._apply_lower_expression_operation(
                tree,
                operation,
                source_trees=source_trees,
            ):
                return False
        if block_operations and not self._apply_lower_block_operations(
            tree,
            block_operations,
            source_trees=source_trees,
        ):
            return False
        if parameter_operations and not self._apply_lower_parameter_operations(
            tree,
            parameter_operations,
            source_trees=source_trees,
        ):
            return False
        if elif_operations and not self._apply_lower_elif_operations(
            tree,
            elif_operations,
            source_trees=source_trees,
        ):
            return False
        if call_argument_operations and not self._apply_lower_call_argument_operations(
            tree,
            call_argument_operations,
            source_trees=source_trees,
        ):
            return False
        return True

    def _lower_materialize_if_supported(self) -> BasicComposable | None:
        native = self._try_native_materialize_if_supported()
        if native is not None:
            return native
        return self._try_lower_materialize_expression_overlay_subset(
            self.lower_materialization_plan()
        )

    def _try_native_materialize_if_supported(self) -> BasicComposable | None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            return None
        root_occurrence_id = self._native_materialization_root()
        if root_occurrence_id is None:
            return None
        root = self._lower_composable_by_occurrence.get(root_occurrence_id)
        if root is None:
            return None
        from astichi.lower_engine.self_native_gates import native_handoff_transfer_enabled

        counters = active_perf_counters()
        handoff_transfer = native_handoff_transfer_enabled()
        try:
            external_literals = {
                overlay_id.index: external_value_to_source(value)
                for overlay_id, value in self._external_value_by_overlay.items()
            }
            if counters is not None and external_literals:
                counters.increment("external_literal_payload", len(external_literals))
            materialize_args = (
                self._native_engine_handle,
                self._native_state_handle,
                external_literals,
                root_occurrence_id.index,
            )
            if counters is None:
                tree = self._native_module.assembly_state_materialize_to_python_ast(
                    *materialize_args
                )
            elif handoff_transfer:
                with counters.measure("copy_python_ast"):
                    tree = self._native_module.assembly_state_materialize_to_python_ast(
                        *materialize_args
                    )
            else:
                with counters.measure("native_materialize_operation_stream"):
                    tree = self._native_module.assembly_state_materialize_to_python_ast(
                        *materialize_args
                    )
        except (TypeError, ValueError, RuntimeError):
            if counters is not None:
                counters.increment("native_materialize_operation_stream_fallback")
            return None
        if not isinstance(tree, ast.Module):
            raise TypeError("native materializer must return ast.Module")
        if counters is not None and not handoff_transfer:
            counters.increment("native_materialize_workspace_copy")
        if _tree_has_unresolved_lower_astichi_demands(tree):
            if counters is not None:
                counters.increment("native_materialize_operation_stream_fallback")
            return None
        return BasicComposable(
            tree=tree,
            origin=root.origin,
            bound_externals=frozenset(),
            _already_materialized=True,
            _executable_handoff_pending=handoff_transfer,
        )

    def _native_materialization_root(self) -> OccurrenceId | None:
        for occurrence in self._lower_state.occurrences:
            if occurrence.parent_occurrence_id is None and occurrence.live:
                return occurrence.occurrence_id
        return None

    def _append_lower_pyimport_hygiene(
        self,
        plan: MaterializationPlan,
    ) -> MaterializationPlan:
        root_id = plan.root_occurrence_id
        if root_id is None:
            return plan
        occurrence = self._lower_engine.occurrence(self._lower_state, root_id)
        package = self._lower_engine.template_package(occurrence.template_id)
        records = tuple(
            row
            for row in package.managed_imports
            if package.managed_import_module_path(row) is not None
        )
        if not records:
            return plan
        final_names = tuple(
            package.managed_import_final_local_name(row)
            for row in records
        )
        collisions = tuple(
            sorted(set(final_names) & package.pyimport_existing_binding_names())
        )
        rename_hygiene = (
            (
                HygieneOperation(
                    operation_key="astichi.operation.rename_if_collides",
                    target_scope_id=0,
                    captures={
                        "colliding_names": list(collisions),
                        "root_occurrence_id": root_id.index,
                    },
                ),
            )
            if collisions
            else ()
        )
        import_hygiene = tuple(
            HygieneOperation(
                operation_key="astichi.operation.managed_import_request",
                target_scope_id=0,
                captures={
                    "final_local_name": package.managed_import_final_local_name(
                        record
                    ),
                    "module_path": ".".join(
                        package.managed_import_module_path(record) or ()
                    ),
                    "original_symbol": package.managed_import_original_symbol(
                        record
                    ),
                    "root_occurrence_id": root_id.index,
                },
            )
            for record in records
        )
        hygiene = rename_hygiene + import_hygiene
        return MaterializationPlan(
            root_occurrence_id=plan.root_occurrence_id,
            operation_stream=plan.operation_stream,
            hygiene_stream=hygiene + plan.hygiene_stream,
            debug_views={
                **plan.debug_views,
                "managed_import_request_count": len(import_hygiene),
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
            source_occurrence = self._lower_engine.occurrence(
                self._lower_state,
                source_id,
            )
            source_package = self._lower_engine.template_package(
                source_occurrence.template_id,
            )
            source_bindings = (
                source_package.binding_names_for_scope_id(
                    source_package.scopes[0].scope_id
                )
                if source_package.scopes
                else frozenset()
            )
            target_occurrence = self._lower_engine.occurrence(
                self._lower_state,
                operation.target_record_id.occurrence_id,
            )
            target_package = self._lower_engine.template_package(
                target_occurrence.template_id,
            )
            target_locator = self._lower_engine.locator_for_record(
                self._lower_state,
                operation.target_record_id,
            )
            target_statement_path = _block_statement_path_for_locator_path(
                target_locator.ast_path
            )
            boundary_names = target_package.boundary_available_names_for_statement_path(
                target_statement_path,
            )
            collisions = tuple(sorted(boundary_names & source_bindings))
            if not collisions:
                continue
            target_scope_id = (
                target_package.scope_id_for_statement_path(target_statement_path)
                or 0
            )
            hygiene.append(
                HygieneOperation(
                    operation_key="astichi.operation.rename_if_collides",
                    target_scope_id=target_scope_id,
                    record_id=operation.target_record_id,
                    captures={
                        "colliding_names": list(collisions),
                        "source_occurrence_id": source_id.index,
                    },
                )
            )
        if not hygiene:
            return plan
        existing_count = int(plan.debug_views.get("boundary_marker_count", 0))
        return MaterializationPlan(
            root_occurrence_id=plan.root_occurrence_id,
            operation_stream=plan.operation_stream,
            hygiene_stream=tuple(hygiene) + plan.hygiene_stream,
            debug_views={
                **plan.debug_views,
                "boundary_marker_count": existing_count + len(hygiene),
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
        final_names = _lower_pyimport_final_names(records)
        if len(final_names) != len(set(final_names)):
            return False
        collisions = _lower_pyimport_colliding_existing_bindings(tree, records)
        if collisions:
            unavailable = _lower_pyimport_existing_binding_names(tree) | set(
                final_names
            )
            rename_counter = 1
            rename_map: dict[str, str] = {}
            for name in collisions:
                next_name, rename_counter = _fresh_lower_scoped_name(
                    name,
                    unavailable | set(rename_map.values()),
                    rename_counter,
                )
                rename_map[name] = next_name
            _rename_lower_module_scope_names(tree, rename_map)
        insert_managed_imports(tree, records)
        _strip_lower_pyimport_declarations(tree)
        return not has_pyimport_marker(recognize_markers(tree))

    def _apply_lower_expression_operation(
        self,
        tree: ast.Module,
        operation: MaterializationOperation,
        *,
        source_trees: dict[OccurrenceId, ast.Module],
    ) -> bool:
        source_id = operation.source_occurrence_id
        if source_id is None:
            return False
        source = self._lower_composable_by_occurrence.get(source_id)
        if source is None:
            return False
        source_tree = source_trees.get(source_id, source.tree)
        source_path = self._source_expression_path(source_id)
        if source_path is None:
            return False
        replacement_node = _source_ast_node_at_path(
            source_tree,
            source.tree,
            source_path,
            ast.expr,
        )
        if replacement_node is None:
            return False
        replacement = clone_ast(replacement_node)
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
        *,
        source_trees: dict[OccurrenceId, ast.Module],
    ) -> bool:
        target_statement_paths: dict[RecordId, str] = {}
        for target_record_id in _ordered_unique_operation_targets(operations):
            target_locator = self._lower_engine.locator_for_record(
                self._lower_state,
                target_record_id,
            )
            target_statement_paths[target_record_id] = (
                _block_statement_path_for_locator(
                    tree,
                    target_locator.ast_path,
                )
            )
        ordered_targets = sorted(
            target_statement_paths,
            key=lambda record_id: _ast_path_sort_key(
                target_statement_paths[record_id]
            ),
            reverse=True,
        )
        for target_record_id in ordered_targets:
            target_locator = self._lower_engine.locator_for_record(
                self._lower_state,
                target_record_id,
            )
            target_statement_path = target_statement_paths[target_record_id]
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
                source_tree = source_trees.get(source_id, source.tree)
                if not self._has_single_block_production(source_id):
                    return False
                if not _lower_boundary_markers_supported_in_tree(
                    source_tree,
                    boundary_names,
                ):
                    return False
                source_bindings = _lower_scope_binding_names(source_tree)
                collisions = emitted_names & source_bindings
                if collisions & source.keep_names:
                    return False
                rename_map: dict[str, str] = {}
                for name in sorted(collisions):
                    next_name, rename_counter = _fresh_lower_scoped_name(
                        name,
                        emitted_names | set(source_bindings) | set(rename_map.values()),
                        rename_counter,
                    )
                    rename_map[name] = next_name
                source_statements = clone_ast(source_tree.body)
                if rename_map:
                    _rename_lower_names(source_statements, rename_map)
                emitted_names.update(source_bindings - collisions)
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
        *,
        source_trees: dict[OccurrenceId, ast.Module],
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
                function_node = None
            if function_node is not None and not _function_has_parameter_hole(
                function_node,
                target_record.resource_name,
            ):
                function_node = None
            if function_node is None:
                function_node = _find_function_with_parameter_hole(
                    tree,
                    target_record.resource_name,
                )
            if function_node is None:
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
                source_tree = source_trees.get(source_id, source.tree)
                payload_path = self._source_parameter_path(source_id)
                if payload_path is None:
                    return False
                payload_node = _source_ast_node_at_path(
                    source_tree,
                    source.tree,
                    payload_path,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                )
                if payload_node is None:
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
        *,
        source_trees: dict[OccurrenceId, ast.Module],
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
                source_tree = source_trees.get(source_id, source.tree)
                payload_path = self._source_elif_path(source_id)
                if payload_path is None:
                    return False
                payload_node = _source_ast_node_at_path(
                    source_tree,
                    source.tree,
                    payload_path,
                    ast.FunctionDef,
                )
                if payload_node is None:
                    return False
                if not _lower_boundary_markers_supported_in_tree(
                    source_tree,
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
        *,
        source_trees: dict[OccurrenceId, ast.Module],
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
            target_node = _ast_node_at_path(tree, placement.call_path)
            if placement.region_name in {"starred", "dstar"}:
                if not isinstance(target_node, ast.Call):
                    return False
            elif placement.region_name == "sequence_starred":
                if not isinstance(target_node, (ast.Tuple, ast.List)):
                    return False
            else:
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
                source_tree = source_trees.get(source_id, source.tree)
                payload_path = self._source_funcargs_path(source_id)
                if payload_path is None:
                    expression_path = self._source_expression_path(source_id)
                    if expression_path is None or placement.region_name not in {
                        "starred",
                        "sequence_starred",
                    }:
                        return False
                    expression = _source_ast_node_at_path(
                        source_tree,
                        source.tree,
                        expression_path,
                        ast.expr,
                    )
                    if expression is None:
                        return False
                    lowered_args.append(clone_ast(expression))
                    continue
                payload_call = _source_ast_node_at_path(
                    source_tree,
                    source.tree,
                    payload_path,
                    ast.Call,
                )
                if payload_call is None:
                    return False
                payload = extract_funcargs_payload(payload_call)
                if placement.region_name in {"starred", "sequence_starred"}:
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
                assert isinstance(target_node, ast.Call)
                target_node.args[placement.index : placement.index + 1] = lowered_args
                continue
            if placement.region_name == "sequence_starred":
                assert isinstance(target_node, (ast.Tuple, ast.List))
                target_node.elts[placement.index : placement.index + 1] = lowered_args
                continue
            assert isinstance(target_node, ast.Call)
            target_node.keywords[placement.index : placement.index + 1] = (
                lowered_keywords
            )
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
        native_candidates = self._find_native_composable_candidates(
            resource,
            selector,
        )
        if native_candidates is not None:
            return native_candidates
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

    def _find_native_composable_candidates(
        self,
        resource: ComposableResource,
        selector: DemandSelector,
    ) -> tuple[BindingCandidate, ...] | None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_template_cache is None
            or self._native_state_handle is None
        ):
            return None
        if not isinstance(resource.composable, BasicComposable):
            raise TypeError(
                "native assembler candidates require BasicComposable resources; "
                f"got {type(resource.composable).__name__}"
            )
        binding = resource.composable._lower_template
        if not isinstance(binding, LowerTemplateBinding):
            raise TypeError("BasicComposable is missing lower template metadata")
        source_template = self._native_template_cache.template_handle_for(binding)
        request = {
            "name": selector.name,
            "build_match": (
                None
                if selector.build_match is None
                else list(selector.build_match)
            ),
            "owner_match": (
                None
                if selector.owner_match is None
                else list(selector.owner_match)
            ),
            "target_inventory_kinds": list(_lower_hole_inventory_kinds()),
            "identifier_bindings": self._native_identifier_bindings_payload(),
        }
        counters = active_perf_counters()
        if counters is not None:
            counters.increment("native_candidate_query_composable")
        result = self._native_module.assembly_state_query_composable_candidates(
            self._native_engine_handle,
            self._native_state_handle,
            source_template,
            request,
        )
        if not isinstance(result, dict):
            raise TypeError("native candidate query result must be a dict")
        raw_candidates = result.get("candidates")
        if not isinstance(raw_candidates, list):
            raise TypeError("native candidate query candidates must be a list")
        production_records = _lower_template_projection_production_records(
            resource.composable
        )
        candidates: list[BindingCandidate] = []
        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, dict):
                raise TypeError("native candidate entry must be a dict")
            target_record_id = self._native_record_id(raw_candidate.get("target_record"))
            target_record = self._visible_lower_projection_record(target_record_id)
            if target_record is None:
                continue
            compatible_productions: list[InventoryRecord] = []
            for index in _native_template_record_indexes(
                raw_candidate.get("production_records")
            ):
                production_record = production_records.get(index)
                if production_record is None:
                    raise TypeError(
                        "native candidate references a non-production template record"
                    )
                compatible_productions.append(production_record)
            candidates.append(
                ComposableCandidate(
                    target_record=target_record,
                    resource=resource,
                    compatible_productions=tuple(compatible_productions),
                )
            )
        if not candidates:
            return None
        return tuple(candidates)

    def _native_record_id(self, value: object) -> RecordId:
        indexes = _native_template_record_indexes(value)
        if len(indexes) != 2:
            raise TypeError("native record id must contain two indexes")
        occurrence_index, template_record_index = indexes
        return RecordId(
            occurrence_id=OccurrenceId(self._lower_state.owner, occurrence_index),
            template_record_id=TemplateRecordId(
                self._lower_state.owner,
                template_record_index,
            ),
        )

    def _find_native_demand_records(
        self,
        selector: DemandSelector,
        *,
        inventory_kinds: tuple[str, ...],
        counter_key: str,
    ) -> tuple[InventoryRecord, ...] | None:
        if (
            self._native_module is None
            or self._native_engine_handle is None
            or self._native_state_handle is None
        ):
            return None
        request = {
            "name": selector.name,
            "build_match": (
                None
                if selector.build_match is None
                else list(selector.build_match)
            ),
            "owner_match": (
                None
                if selector.owner_match is None
                else list(selector.owner_match)
            ),
            "target_inventory_kinds": list(inventory_kinds),
            "identifier_bindings": self._native_identifier_bindings_payload(),
        }
        counters = active_perf_counters()
        if counters is not None:
            counters.increment(counter_key)
        result = self._native_module.assembly_state_query_demand_candidates(
            self._native_engine_handle,
            self._native_state_handle,
            request,
        )
        if not isinstance(result, dict):
            raise TypeError("native demand query result must be a dict")
        raw_candidates = result.get("candidates")
        if not isinstance(raw_candidates, list):
            raise TypeError("native demand query candidates must be a list")
        records: list[InventoryRecord] = []
        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, dict):
                raise TypeError("native demand candidate entry must be a dict")
            record = self._visible_lower_projection_record(
                self._native_record_id(raw_candidate.get("target_record"))
            )
            if record is not None:
                records.append(record)
        if not records:
            return None
        return tuple(records)

    def _native_identifier_bindings_payload(self) -> list[list[object]]:
        return []

    def _find_lower_external_candidates(
        self,
        resource: ExternalValueResource,
        selector: DemandSelector,
    ) -> tuple[BindingCandidate, ...]:
        native_records = self._find_native_demand_records(
            selector,
            inventory_kinds=("external.bind",),
            counter_key="native_candidate_query_external",
        )
        if native_records is not None:
            return tuple(
                ExternalValueCandidate(demand_record=record, resource=resource)
                for record in native_records
            )
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
        native_records = self._find_native_demand_records(
            selector,
            inventory_kinds=("identifier.demand",),
            counter_key="native_candidate_query_identifier",
        )
        if native_records is not None:
            return tuple(
                IdentifierNameCandidate(demand_record=record, resource=resource)
                for record in native_records
            )
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


def _source_ast_node_at_path(
    materialized_root: ast.AST,
    template_root: ast.AST,
    path: str,
    expected_type: type[ast.AST] | tuple[type[ast.AST], ...],
) -> ast.AST | None:
    node = _maybe_ast_node_at_path(materialized_root, path)
    if isinstance(node, expected_type):
        return node
    fallback = _maybe_ast_node_at_path(template_root, path)
    if isinstance(fallback, expected_type):
        return fallback
    return None


def _maybe_ast_node_at_path(root: ast.AST, path: str) -> ast.AST | None:
    try:
        return _ast_node_at_path(root, path)
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


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


def _ast_path_sort_key(path: str) -> tuple[int, tuple[tuple[str, int], ...]]:
    parts = path.split("/") if path else ()
    return (
        len(parts),
        tuple(
            (field_name, -1 if index is None else index)
            for field_name, index in (_ast_path_part(part) for part in parts)
        ),
    )


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


def _block_statement_path_for_locator_path(path: str) -> str:
    if path.endswith("/value"):
        return _statement_path_for_marker_locator(path)
    return path


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


def _function_has_parameter_hole(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
) -> bool:
    return any(
        param_hole_name(argument) == name
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
    )


def _find_function_with_parameter_hole(
    tree: ast.Module,
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    matches = tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _function_has_parameter_hole(node, name)
    )
    if len(matches) != 1:
        return None
    return matches[0]


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
        if separator and suffix.endswith("]/value"):
            index_text = suffix.removesuffix("]/value")
            if not index_text.isdigit():
                return None
            return _CallArgumentPlacement(
                call_path=call_path,
                index=int(index_text),
                region_name="starred",
            )
        sequence_path, separator, suffix = path.partition("/elts[")
        if separator and suffix.endswith("]/value"):
            index_text = suffix.removesuffix("]/value")
            if not index_text.isdigit():
                return None
            return _CallArgumentPlacement(
                call_path=sequence_path,
                index=int(index_text),
                region_name="sequence_starred",
            )
        return None
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
    return _lower_boundary_marker_tuple_supported(source.markers, available_names)


def _lower_boundary_markers_supported_in_tree(
    tree: ast.Module,
    available_names: frozenset[str],
) -> bool:
    from astichi.lowering import recognize_markers

    return _lower_boundary_marker_tuple_supported(
        recognize_markers(tree),
        available_names,
    )


def _lower_boundary_marker_tuple_supported(
    markers: Iterable[object],
    available_names: frozenset[str],
) -> bool:
    from astichi.lowering.markers import (
        boundary_explicit_bind_enabled,
        boundary_outer_bind_enabled,
    )

    for marker in markers:
        source_name = getattr(marker, "source_name", None)
        if source_name == "astichi_elif":
            continue
        if source_name == "astichi_export":
            continue
        if source_name not in {"astichi_import", "astichi_pass"}:
            return False
        node = getattr(marker, "node", None)
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

        def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
            replacement = _lower_pass_sentinel_replacement(node)
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


def _lower_pass_sentinel_replacement(node: ast.Attribute) -> ast.expr | None:
    sentinel = match_transparent_sentinel(
        node,
        is_marker_call=_is_lower_pass_call,
    )
    if sentinel is None:
        return None
    name = _lower_boundary_call_name(sentinel.call)
    if name is None:
        return None
    replacement = ast.Name(id=name, ctx=sentinel.ctx)
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


def _is_lower_pass_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == "astichi_pass"
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


def _lower_pyimport_final_names(records: Iterable[object]) -> tuple[str, ...]:
    return tuple(
        name
        for record in records
        if isinstance((name := getattr(record, "final_local_name", None)), str)
    )


def _lower_pyimport_colliding_existing_bindings(
    tree: ast.Module,
    records: Iterable[object],
) -> tuple[str, ...]:
    final_names = _lower_pyimport_final_names(records)
    bindings = _lower_pyimport_existing_binding_names(tree)
    return tuple(sorted(set(final_names) & bindings))


def _lower_pyimport_existing_binding_names(tree: ast.Module) -> set[str]:
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
    return bindings


def _rename_lower_module_scope_names(
    tree: ast.Module,
    rename_map: dict[str, str],
) -> None:
    class _Renamer(ast.NodeTransformer):
        def visit_Expr(self, node: ast.Expr) -> ast.AST:
            if _is_lower_pyimport_call(node.value):
                return node
            return self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> ast.AST:
            replacement = rename_map.get(node.id)
            if replacement is not None:
                node.id = replacement
            return node

        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            replacement = rename_map.get(node.name)
            if replacement is not None:
                node.name = replacement
            return node

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
            replacement = rename_map.get(node.name)
            if replacement is not None:
                node.name = replacement
            return node

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
            replacement = rename_map.get(node.name)
            if replacement is not None:
                node.name = replacement
            return node

    renamer = _Renamer()
    for statement in tree.body:
        renamer.visit(statement)


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


def _tree_has_unresolved_lower_astichi_demands(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if _node_is_unresolved_lower_call_demand(node):
            return True
        if _node_has_unresolved_lower_suffix_demand(node):
            return True
    return False


def _node_is_unresolved_lower_call_demand(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name):
        return False
    return node.func.id in _UNRESOLVED_LOWER_CALL_DEMANDS


def _node_has_unresolved_lower_suffix_demand(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return _name_has_unresolved_lower_suffix_demand(node.id)
    if isinstance(node, ast.arg):
        return _name_has_unresolved_lower_suffix_demand(node.arg)
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return _name_has_unresolved_lower_suffix_demand(node.name)
    if isinstance(node, ast.alias):
        if _name_has_unresolved_lower_suffix_demand(node.name):
            return True
        return (
            node.asname is not None
            and _name_has_unresolved_lower_suffix_demand(node.asname)
        )
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return any(
            _name_has_unresolved_lower_suffix_demand(part)
            for part in node.module.split(".")
        )
    return False


def _name_has_unresolved_lower_suffix_demand(name: str) -> bool:
    _, marker = strip_identifier_suffix(name)
    return marker is ARG_IDENTIFIER or marker is PARAM_HOLE_IDENTIFIER


def _operations_by_target_occurrence(
    plan: MaterializationPlan,
) -> dict[OccurrenceId, tuple[MaterializationOperation, ...]]:
    grouped: dict[OccurrenceId, list[MaterializationOperation]] = {}
    for operation in plan.operation_stream:
        grouped.setdefault(
            operation.target_record_id.occurrence_id,
            [],
        ).append(operation)
    return {
        occurrence_id: tuple(operations)
        for occurrence_id, operations in grouped.items()
    }


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


def _native_template_record_indexes(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise TypeError("native record index payload must be a list")
    indexes: list[int] = []
    for item in value:
        if not isinstance(item, int):
            raise TypeError("native record index entries must be integers")
        indexes.append(item)
    return tuple(indexes)


def _native_scope_mirror_replay_enabled() -> bool:
    """Opt-in compatibility path that mirrors native batch results into Python lower state."""
    from astichi.lower_engine.native import native_capabilities

    capabilities = native_capabilities()
    if capabilities is not None:
        features = capabilities.get("engine_features", ())
        if "native.self_native.scope_no_mirror_replay.v1" in features:
            return False
    value = os.environ.get("ASTICHI_NATIVE_SCOPE_MIRROR_REPLAY", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _string_field(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise TypeError(f"native batch field {key} must be a string")
    return value


def _string_tuple_field(mapping: dict[str, object], key: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise TypeError(f"native batch field {key} must be a list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"native batch field {key} entries must be strings")
        items.append(item)
    return tuple(items)


def _assert_native_overlay_alignment(
    event: dict[str, object],
    expected_overlay_index: int,
) -> None:
    overlay_id = event.get("overlay_id")
    if not isinstance(overlay_id, int):
        raise TypeError("native batch overlay_id must be an int")
    if overlay_id != expected_overlay_index:
        raise RuntimeError(
            "native/Python overlay mirror diverged: "
            f"native={overlay_id}, python={expected_overlay_index}"
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
def find_candidates_in_inventory(
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


def _select_batch_candidate(
    candidates: tuple[BindingCandidate, ...],
    *,
    allow_equivalent_demand_sites: bool,
) -> BindingCandidate:
    if not allow_equivalent_demand_sites or len(candidates) <= 1:
        return require_one(candidates)
    first = candidates[0]
    first_record = _candidate_demand_record(first)
    if first_record is None:
        return require_one(candidates)
    for candidate in candidates[1:]:
        record = _candidate_demand_record(candidate)
        if (
            record is None
            or record.build_path != first_record.build_path
            or record.code_owner != first_record.code_owner
            or record.name != first_record.name
            or record.kind != first_record.kind
        ):
            return require_one(candidates)
    return first


def _candidate_demand_record(
    candidate: BindingCandidate,
) -> InventoryRecord | None:
    if isinstance(candidate, ComposableCandidate):
        return candidate.target_record
    if isinstance(candidate, ExternalValueCandidate | IdentifierNameCandidate):
        return candidate.demand_record
    return None


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


def _lower_template_projection_production_records(
    composable: BasicComposable,
) -> dict[int, InventoryRecord]:
    binding = composable._lower_template
    if not isinstance(binding, LowerTemplateBinding):
        raise TypeError("BasicComposable is missing lower template metadata")
    records: dict[int, InventoryRecord] = {}
    for index, spec in enumerate(binding.record_specs):
        record = spec.projection_record
        if isinstance(record, InventoryRecord) and record.kind.startswith(
            "production."
        ):
            records[index] = record
    return records


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
    if isinstance(node, LocatedStaticCodePathNode):
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
