"""Lower-engine materialization plan data."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from astichi.lower_engine.handles import OccurrenceId, OverlayId, RecordId
from astichi.lower_engine.inventory import AssemblyState
from astichi.perf_counters import counted_perf_call

_EXTERNAL_BIND_OPERATION = "astichi.operation.lower_external_ref"
_IDENTIFIER_BIND_OPERATION = "astichi.operation.rewrite_identifier"
_HYGIENE_GATE_OPERATION = "astichi.operation.gate_no_unresolved"


@dataclass(frozen=True, slots=True)
class MaterializationOperation:
    operation_key: str
    target_record_id: RecordId
    source_occurrence_id: OccurrenceId | None = None
    overlay_id: OverlayId | None = None
    order: int = 0
    captures: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HygieneOperation:
    operation_key: str
    target_scope_id: int
    record_id: RecordId | None = None
    captures: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MaterializationPlan:
    root_occurrence_id: OccurrenceId | None = None
    operation_stream: tuple[MaterializationOperation, ...] = ()
    hygiene_stream: tuple[HygieneOperation, ...] = ()
    debug_views: Mapping[str, Any] = field(default_factory=dict)
    artifact_requests: tuple[str, ...] = ()


@counted_perf_call("lower_materialization_plan")
def build_materialization_plan(
    state: AssemblyState,
    *,
    root_occurrence_id: OccurrenceId | None = None,
    registered_operation_keys: Collection[str] | None = None,
) -> MaterializationPlan:
    """Build a deterministic lower-owned materialization plan for ``state``."""
    root = root_occurrence_id or _default_root_occurrence_id(state)
    operations = (
        *_edge_operations(state),
        *_overlay_operations(state),
    )
    hygiene = (
        HygieneOperation(
            operation_key=_HYGIENE_GATE_OPERATION,
            target_scope_id=0,
            captures={
                "live_record_count": _live_record_count(state),
                "root_occurrence_id": None if root is None else root.index,
                "satisfied_record_count": len(state.satisfied_records),
            },
        ),
    )
    _validate_operation_keys(
        (
            *(operation.operation_key for operation in operations),
            *(operation.operation_key for operation in hygiene),
        ),
        registered_operation_keys,
    )
    return MaterializationPlan(
        root_occurrence_id=root,
        operation_stream=operations,
        hygiene_stream=hygiene,
        debug_views={
            "edge_count": len(state.edges),
            "overlay_count": len(state.overlays),
        },
        artifact_requests=("python_ast",),
    )


def _edge_operations(state: AssemblyState) -> tuple[MaterializationOperation, ...]:
    return tuple(
        MaterializationOperation(
            operation_key=edge.operation_key,
            target_record_id=edge.target_record_id,
            source_occurrence_id=edge.source_occurrence_id,
            order=edge.order,
            captures={
                "edge_id": edge.edge_id.index,
                "target_state": _record_state(state, edge.target_record_id),
            },
        )
        for edge in sorted(state.edges, key=lambda item: item.edge_id.index)
    )


def _overlay_operations(state: AssemblyState) -> tuple[MaterializationOperation, ...]:
    return tuple(
        MaterializationOperation(
            operation_key=_overlay_operation_key(overlay.kind),
            target_record_id=overlay.target_record_id,
            overlay_id=overlay.overlay_id,
            captures={
                "overlay_id": overlay.overlay_id.index,
                "overlay_kind": overlay.kind,
                "source_label": overlay.source_label,
                "target_state": _record_state(state, overlay.target_record_id),
            },
        )
        for overlay in sorted(state.overlays, key=lambda item: item.overlay_id.index)
    )


def _overlay_operation_key(kind: str) -> str:
    if kind == "external":
        return _EXTERNAL_BIND_OPERATION
    if kind == "identifier":
        return _IDENTIFIER_BIND_OPERATION
    return f"astichi.operation.overlay.{kind}"


def _default_root_occurrence_id(state: AssemblyState) -> OccurrenceId | None:
    for occurrence in state.occurrences:
        if occurrence.parent_occurrence_id is None and occurrence.live:
            return occurrence.occurrence_id
    return None


def _live_record_count(state: AssemblyState) -> int:
    return sum(
        1
        for record_ids in state.indexes.by_build_path.values()
        for record_id in record_ids
        if _record_state(state, record_id) == "live"
    )


def _record_state(state: AssemblyState, record_id: RecordId) -> str:
    occurrence = state.occurrences[record_id.occurrence_id.index]
    if not occurrence.live or record_id in state.dead_records:
        return "dead"
    if record_id in state.satisfied_records:
        return "satisfied"
    return "live"


def _validate_operation_keys(
    operation_keys: tuple[str, ...],
    registered_operation_keys: Collection[str] | None,
) -> None:
    if registered_operation_keys is None:
        return
    registered = frozenset(registered_operation_keys)
    missing = sorted(set(operation_keys) - registered)
    if missing:
        raise ValueError(f"unregistered materialization operation keys: {missing}")
