"""Structural snapshot projection for lower-engine state."""

from __future__ import annotations

from typing import Any

from astichi.lower_engine.handles import (
    EdgeId,
    OccurrenceId,
    OverlayId,
    RecordId,
    TemplateId,
    TemplateRecordId,
)
from astichi.lower_engine.inventory import AssemblyState
from astichi.lower_engine.materialization import (
    HygieneOperation,
    MaterializationOperation,
    MaterializationPlan,
)
from astichi.lower_engine.registry import RegisteredSurfaceBundle
from astichi.lower_engine.templates import Template
from astichi.structural_snapshot import SCHEMA


def structural_snapshot(
    *,
    templates: tuple[Template, ...],
    state: AssemblyState,
    materialization_plan: MaterializationPlan | None = None,
    surface_bundle: RegisteredSurfaceBundle | None = None,
) -> dict[str, Any]:
    """Render lower-engine state as a structural snapshot mapping."""
    plan = materialization_plan or MaterializationPlan()
    return {
        "schema": SCHEMA,
        "surface_bundle": (
            surface_bundle.snapshot()
            if surface_bundle is not None
            else {
                "bundle_key": "astichi.lower_engine.skeleton",
                "operations": [],
                "patterns": [],
                "schema_version": 1,
                "surfaces": [],
            }
        ),
        "templates": [_template_snapshot(template) for template in templates],
        "locators": [
            locator
            for template in templates
            for locator in template.package_v2.structural_locator_snapshots(
                template_id=_template_index(template.template_id)
            )
        ],
        "occurrences": [
            {
                "build_path": list(occurrence.build_path),
                "occurrence_id": _occurrence_index(occurrence.occurrence_id),
                "parent_occurrence_id": _optional_occurrence_index(
                    occurrence.parent_occurrence_id
                ),
                "template_id": _template_index(occurrence.template_id),
            }
            for occurrence in state.occurrences
        ],
        "records": [
            _record_snapshot(record_id=record_id, state=state, templates=templates)
            for occurrence in state.occurrences
            for record_id in _record_ids_for_occurrence(occurrence, templates)
        ],
        "edges": [
            {
                "edge_id": _edge_index(edge.edge_id),
                "operation_key": edge.operation_key,
                "order": edge.order,
                "source_occurrence_id": _occurrence_index(edge.source_occurrence_id),
                "target_record_id": _record_id_array(edge.target_record_id),
            }
            for edge in state.edges
        ],
        "overlays": [
            {
                "kind": overlay.kind,
                "overlay_id": _overlay_index(overlay.overlay_id),
                "source_label": overlay.source_label,
                "target_record_id": _record_id_array(overlay.target_record_id),
            }
            for overlay in state.overlays
        ],
        "materialization": _materialization_snapshot(plan),
        "diagnostics": [],
    }


def _template_snapshot(template: Template) -> dict[str, Any]:
    return template.package_v2.structural_template_snapshot(
        template_id=_template_index(template.template_id)
    )


def _record_snapshot(
    *,
    record_id: RecordId,
    state: AssemblyState,
    templates: tuple[Template, ...],
) -> dict[str, Any]:
    template_record = _template_record(
        record_id=record_id,
        state=state,
        templates=templates,
    )
    occurrence = state.occurrences[record_id.occurrence_id.index]
    template = _template(occurrence.template_id, templates)
    resolved_state = _record_state(record_id=record_id, state=state)
    return template.package_v2.structural_record_snapshot(
        template_record_id=_template_record_index(template_record.template_record_id),
        occurrence_id=_occurrence_index(record_id.occurrence_id),
        visible=resolved_state == "live",
        satisfied=resolved_state == "satisfied",
    )


def _materialization_snapshot(plan: MaterializationPlan) -> dict[str, Any]:
    return {
        "artifact_requests": list(plan.artifact_requests),
        "debug_views": dict(plan.debug_views),
        "hygiene_stream": [
            _hygiene_operation_snapshot(operation)
            for operation in plan.hygiene_stream
        ],
        "operation_stream": [
            _materialization_operation_snapshot(operation)
            for operation in plan.operation_stream
        ],
        "root_occurrence_id": _optional_occurrence_index(plan.root_occurrence_id),
    }


def _materialization_operation_snapshot(
    operation: MaterializationOperation,
) -> dict[str, Any]:
    return {
        "captures": dict(operation.captures),
        "operation_key": operation.operation_key,
        "order": operation.order,
        "overlay_id": _optional_overlay_index(operation.overlay_id),
        "source_occurrence_id": _optional_occurrence_index(
            operation.source_occurrence_id
        ),
        "target_record_id": _record_id_array(operation.target_record_id),
    }


def _hygiene_operation_snapshot(operation: HygieneOperation) -> dict[str, Any]:
    return {
        "captures": dict(operation.captures),
        "operation_key": operation.operation_key,
        "record_id": (
            None
            if operation.record_id is None
            else _record_id_array(operation.record_id)
        ),
        "target_scope_id": operation.target_scope_id,
    }


def _record_ids_for_occurrence(occurrence: Any, templates: tuple[Template, ...]) -> tuple[RecordId, ...]:
    template = _template(occurrence.template_id, templates)
    return tuple(
        RecordId(
            occurrence_id=occurrence.occurrence_id,
            template_record_id=record.template_record_id,
        )
        for record in template.records
    )


def _template(template_id: TemplateId, templates: tuple[Template, ...]) -> Template:
    for template in templates:
        if template.template_id == template_id:
            return template
    raise KeyError(f"unknown template id: {template_id.index}")


def _template_record(
    *,
    record_id: RecordId,
    state: AssemblyState,
    templates: tuple[Template, ...],
) -> Any:
    occurrence = state.occurrences[record_id.occurrence_id.index]
    template = _template(occurrence.template_id, templates)
    for record in template.records:
        if record.template_record_id == record_id.template_record_id:
            return record
    raise KeyError(
        f"unknown template record id: {record_id.template_record_id.index}"
    )


def _record_state(*, record_id: RecordId, state: AssemblyState) -> str:
    occurrence = state.occurrences[record_id.occurrence_id.index]
    if not occurrence.live or record_id in state.dead_records:
        return "dead"
    if record_id in state.satisfied_records:
        return "satisfied"
    return "live"


def _record_id_array(record_id: RecordId) -> list[int]:
    return [
        _occurrence_index(record_id.occurrence_id),
        _template_record_index(record_id.template_record_id),
    ]


def _template_index(template_id: TemplateId) -> int:
    return template_id.index


def _template_record_index(template_record_id: TemplateRecordId) -> int:
    return template_record_id.index


def _occurrence_index(occurrence_id: OccurrenceId) -> int:
    return occurrence_id.index


def _optional_occurrence_index(occurrence_id: OccurrenceId | None) -> int | None:
    return None if occurrence_id is None else _occurrence_index(occurrence_id)


def _edge_index(edge_id: EdgeId) -> int:
    return edge_id.index


def _overlay_index(overlay_id: OverlayId) -> int:
    return overlay_id.index


def _optional_overlay_index(overlay_id: OverlayId | None) -> int | None:
    return None if overlay_id is None else _overlay_index(overlay_id)
