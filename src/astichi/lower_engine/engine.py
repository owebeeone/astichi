"""Private Python lower-engine skeleton."""

from __future__ import annotations

from itertools import count

from astichi.lower_engine.errors import StaleHandleError
from astichi.lower_engine.handles import (
    EdgeId,
    EngineOwner,
    LocatorId,
    OccurrenceId,
    OverlayId,
    RecordId,
    TemplateId,
    TemplateRecordId,
)
from astichi.lower_engine.inventory import (
    AssemblyEdge,
    AssemblyState,
    Occurrence,
    Overlay,
)
from astichi.lower_engine.materialization import (
    HygieneOperation,
    MaterializationOperation,
    MaterializationPlan,
    build_materialization_plan,
)
from astichi.lower_engine.package_v2 import LowerTemplatePackageV2
from astichi.lower_engine.registry import SurfaceRegistry
from astichi.lower_engine.snapshots import structural_snapshot
from astichi.lower_engine.templates import (
    SourceLocator,
    Template,
    TemplateCommentMarkerSpec,
    TemplateMarkerSpec,
    TemplatePyImportMarkerSpec,
    TemplateRefMarkerSpec,
    TemplateRecord,
    TemplateRecordSpec,
    TemplateScopeSpec,
    TemplateUnrollMarkerSpec,
)

_OWNER_IDS = count()
PYTHON_PACKAGE_V2_FEATURE = "python.lower_template_package_v2.v1"
PYTHON_PACKAGE_ONLY_PLAN_FEATURE = "python.materialization_plan.package_only.v1"


def _is_unresolved_capable_inventory_kind(inventory_kind: str) -> bool:
    return (
        inventory_kind.startswith("hole.")
        or inventory_kind.endswith(".demand")
        or inventory_kind == "external.bind"
    )


class LowerEngine:
    """Private lower-engine table owner for tests and migration fixtures."""

    def __init__(self, *, owner_label: str = "python-reference") -> None:
        self._owner = EngineOwner(next(_OWNER_IDS))
        self._owner_label = owner_label
        self._templates: list[Template] = []
        self._next_locator_index = 0
        self.surface_registry = SurfaceRegistry(self._owner)

    def register_template(
        self,
        *,
        template_key: str,
        source_summary: str,
        records: tuple[TemplateRecordSpec, ...],
        scopes: tuple[TemplateScopeSpec, ...] = (),
        markers: tuple[TemplateMarkerSpec, ...] = (),
        pyimport_markers: tuple[TemplatePyImportMarkerSpec, ...] = (),
        comment_markers: tuple[TemplateCommentMarkerSpec, ...] = (),
        ref_markers: tuple[TemplateRefMarkerSpec, ...] = (),
        unroll_markers: tuple[TemplateUnrollMarkerSpec, ...] = (),
    ) -> TemplateId:
        """Register immutable template metadata and return its handle."""
        template_id = TemplateId(owner=self._owner, index=len(self._templates))
        locators: list[SourceLocator] = []
        template_records: list[TemplateRecord] = []
        package = LowerTemplatePackageV2(
            template_key=template_key,
            source_summary=source_summary,
            surface_bundle_signature=(
                ""
                if self.surface_registry.bundle is None
                else self.surface_registry.bundle.bundle_signature
            ),
        )
        for spec in records:
            locator_id = LocatorId(
                owner=self._owner,
                index=self._next_locator_index,
            )
            self._next_locator_index += 1
            record_id = TemplateRecordId(
                owner=self._owner,
                index=len(template_records),
            )
            package.add_locator(
                ast_path=spec.ast_path,
                role_key=spec.role_key,
                authored_summary=spec.authored_summary,
                materialization_anchor=spec.materialization_anchor,
                locator_id=locator_id.index,
            )
            package.add_record(
                surface_key=spec.surface_key,
                locator_id=locator_id.index,
                inventory_kind=spec.inventory_kind,
                owner_path=spec.code_owner_parts,
                semantic_summary=spec.semantic_summary,
                resource_name=spec.resource_name,
                template_record_id=record_id.index,
            )
            locators.append(
                SourceLocator(
                    locator_id=locator_id,
                    template_id=template_id,
                    ast_path=spec.ast_path,
                    role_key=spec.role_key,
                    parent_locator_id=None,
                    authored_summary=spec.authored_summary,
                    materialization_anchor=spec.materialization_anchor,
                )
            )
            template_records.append(
                TemplateRecord(
                    template_record_id=record_id,
                    surface_key=spec.surface_key,
                    semantic_summary=spec.semantic_summary,
                    locator_id=locator_id,
                    surface_id=spec.surface_id,
                    resource_name=spec.resource_name,
                    inventory_kind=spec.inventory_kind,
                    code_owner_parts=spec.code_owner_parts,
                    legacy_record_id=spec.legacy_record_id,
                    projection_record=spec.projection_record,
                )
            )
        for spec in scopes:
            package.add_scope(
                scope_kind=spec.scope_kind,
                ast_path=spec.ast_path,
                owner_path=spec.owner_path,
                local_bindings=spec.local_bindings,
                arguments=spec.arguments,
                parent_scope_id=spec.parent_scope_id,
                start_line=spec.start_line,
            )
        for spec in markers:
            package.add_marker(
                marker_kind=spec.marker_kind,
                source_name=spec.source_name,
                ast_path=spec.ast_path,
                statement_path=spec.statement_path,
                owner_path=spec.owner_path,
                scope_id=spec.scope_id,
                source_order=spec.source_order,
                resource_name=spec.resource_name,
                operation_key=spec.operation_key,
                flags=spec.flags,
            )
        for spec in pyimport_markers:
            package.add_pyimport_marker(
                marker_id=spec.marker_id,
                module_path=spec.module_path,
                names=spec.names,
                as_name=spec.as_name,
                flags=spec.flags,
            )
        for spec in comment_markers:
            package.add_comment_marker(
                marker_id=spec.marker_id,
                payload=spec.payload,
                flags=spec.flags,
            )
        for spec in ref_markers:
            package.add_ref_marker(
                marker_id=spec.marker_id,
                ref_kind=spec.ref_kind,
                context=spec.context,
                sentinel_attr=spec.sentinel_attr,
                literal_path=spec.literal_path,
                flags=spec.flags,
            )
        for spec in unroll_markers:
            package.add_unroll_marker(
                marker_id=spec.marker_id,
                statement_path=spec.statement_path,
                target_ast_path=spec.target_ast_path,
                iter_ast_path=spec.iter_ast_path,
                domain_ast_path=spec.domain_ast_path,
                body_path=spec.body_path,
                orelse_path=spec.orelse_path,
                target_bindings=spec.target_bindings,
                domain_shape=spec.domain_shape,
                flags=spec.flags,
            )
        self._templates.append(
            Template(
                template_id=template_id,
                template_key=template_key,
                source_summary=source_summary,
                locators=tuple(locators),
                records=tuple(template_records),
                package_v2=package,
            )
        )
        return template_id

    def new_state(self) -> AssemblyState:
        """Create a mutable assembly state owned by this engine."""
        return AssemblyState(owner=self._owner, owner_label=self._owner_label)

    def capabilities(self) -> dict[str, object]:
        """Return Python lower-engine capability metadata."""
        return {
            "backend_label": self._owner_label,
            "engine_features": [
                PYTHON_PACKAGE_V2_FEATURE,
                PYTHON_PACKAGE_ONLY_PLAN_FEATURE,
            ],
            "lower_template_package_v2": True,
        }

    def append_occurrence(
        self,
        state: AssemblyState,
        template_id: TemplateId,
        *,
        build_path: tuple[str, ...],
        parent_occurrence_id: OccurrenceId | None = None,
        overlay_id: OverlayId | None = None,
    ) -> OccurrenceId:
        """Append a template occurrence and derive its live records."""
        self._check_state(state)
        self._check_template_id(template_id)
        if parent_occurrence_id is not None:
            self._check_occurrence_id(parent_occurrence_id)
        if overlay_id is not None:
            self._check_overlay_id(overlay_id)

        occurrence_id = OccurrenceId(owner=self._owner, index=len(state.occurrences))
        occurrence = Occurrence(
            occurrence_id=occurrence_id,
            template_id=template_id,
            build_path=build_path,
            parent_occurrence_id=parent_occurrence_id,
            overlay_id=overlay_id,
        )
        state.occurrences.append(occurrence)

        template = self._template(template_id)
        for record in template.records:
            record_id = RecordId(
                occurrence_id=occurrence_id,
                template_record_id=record.template_record_id,
            )
            state.indexes.append(
                build_path=build_path,
                surface_key=record.surface_key,
                resource_name=record.resource_name,
                inventory_kind=record.inventory_kind,
                code_owner_parts=record.code_owner_parts,
                record_id=record_id,
            )
        return occurrence_id

    def append_edge(
        self,
        state: AssemblyState,
        *,
        target_record_id: RecordId,
        source_occurrence_id: OccurrenceId,
        operation_key: str,
        order: int = 0,
    ) -> EdgeId:
        """Append a composable insertion edge."""
        self._check_state(state)
        self._check_record_id(target_record_id)
        self._check_occurrence_id(source_occurrence_id)
        edge_id = EdgeId(owner=self._owner, index=len(state.edges))
        state.edges.append(
            AssemblyEdge(
                edge_id=edge_id,
                target_record_id=target_record_id,
                source_occurrence_id=source_occurrence_id,
                operation_key=operation_key,
                order=order,
            )
        )
        return edge_id

    def append_overlay(
        self,
        state: AssemblyState,
        *,
        kind: str,
        source_label: str,
        target_record_id: RecordId,
    ) -> OverlayId:
        """Append an overlay binding record."""
        self._check_state(state)
        self._check_record_id(target_record_id)
        overlay_id = OverlayId(owner=self._owner, index=len(state.overlays))
        state.overlays.append(
            Overlay(
                overlay_id=overlay_id,
                kind=kind,
                source_label=source_label,
                target_record_id=target_record_id,
            )
        )
        return overlay_id

    def mark_satisfied(self, state: AssemblyState, record_id: RecordId) -> None:
        """Mark a derived record satisfied."""
        self._check_state(state)
        self._check_record_id(record_id)
        state.satisfied_records.add(record_id)

    def record_id(
        self,
        state: AssemblyState,
        occurrence_id: OccurrenceId,
        template_record_index: int,
    ) -> RecordId:
        """Build a derived record handle for one occurrence/template record."""
        self._check_state(state)
        self._check_occurrence_id(occurrence_id)
        occurrence = state.occurrences[occurrence_id.index]
        template = self._template(occurrence.template_id)
        template_record = template.records[template_record_index]
        return RecordId(
            occurrence_id=occurrence_id,
            template_record_id=template_record.template_record_id,
        )

    def occurrence(
        self,
        state: AssemblyState,
        occurrence_id: OccurrenceId,
    ) -> Occurrence:
        """Return one occurrence record after validating its handle."""
        self._check_state(state)
        self._check_occurrence_id(occurrence_id)
        return state.occurrences[occurrence_id.index]

    def template_record(
        self,
        state: AssemblyState,
        record_id: RecordId,
    ) -> TemplateRecord:
        """Return the template record addressed by a derived record handle."""
        self._check_state(state)
        self._check_record_id(record_id)
        occurrence = self.occurrence(state, record_id.occurrence_id)
        template = self._template(occurrence.template_id)
        return template.records[record_id.template_record_id.index]

    def locator_for_record(
        self,
        state: AssemblyState,
        record_id: RecordId,
    ) -> SourceLocator:
        """Return the source locator associated with one derived record."""
        occurrence = self.occurrence(state, record_id.occurrence_id)
        template = self._template(occurrence.template_id)
        template_record = template.records[record_id.template_record_id.index]
        for locator in template.locators:
            if locator.locator_id == template_record.locator_id:
                return locator
        raise KeyError(
            f"unknown locator for record: {record_id.template_record_id.index}"
        )

    def template_records_for_occurrence(
        self,
        state: AssemblyState,
        occurrence_id: OccurrenceId,
    ) -> tuple[TemplateRecord, ...]:
        """Return template records for one occurrence."""
        occurrence = self.occurrence(state, occurrence_id)
        return self._template(occurrence.template_id).records

    def template_package(self, template_id: TemplateId) -> LowerTemplatePackageV2:
        """Return the v2 lower-template package for a registered template."""
        self._check_template_id(template_id)
        return self._template(template_id).package_v2

    def structural_snapshot(
        self,
        state: AssemblyState,
        *,
        materialization_plan: MaterializationPlan | None = None,
    ) -> dict[str, object]:
        """Project current state to the canonical structural snapshot shape."""
        self._check_state(state)
        return structural_snapshot(
            templates=tuple(self._templates),
            state=state,
            materialization_plan=materialization_plan,
            surface_bundle=self.surface_registry.bundle,
        )

    def build_materialization_plan(
        self,
        state: AssemblyState,
        *,
        root_occurrence_id: OccurrenceId | None = None,
    ) -> MaterializationPlan:
        """Build a lower-owned materialization plan for one assembly state."""
        self._check_state(state)
        if root_occurrence_id is not None:
            self._check_occurrence_id(root_occurrence_id)
        bundle = self.surface_registry.bundle
        operation_keys = (
            None
            if bundle is None
            else tuple(operation.operation_key for operation in bundle.operations)
        )
        plan = build_materialization_plan(
            state,
            root_occurrence_id=root_occurrence_id,
            registered_operation_keys=operation_keys,
        )
        plan = self._with_package_gate_captures(state, plan)
        fallback_operations = self._defaulted_block_fallback_operations(state)
        if fallback_operations:
            plan = MaterializationPlan(
                root_occurrence_id=plan.root_occurrence_id,
                operation_stream=plan.operation_stream + fallback_operations,
                hygiene_stream=plan.hygiene_stream,
                debug_views={
                    **plan.debug_views,
                    "fallback_operation_count": len(fallback_operations),
                },
                artifact_requests=plan.artifact_requests,
            )
        return self._append_package_marker_hygiene(state, plan)

    def _with_package_gate_captures(
        self,
        state: AssemblyState,
        plan: MaterializationPlan,
    ) -> MaterializationPlan:
        unresolved_capable = self._unresolved_capable_records(state)
        unresolved_live = tuple(
            record_id
            for record_id in unresolved_capable
            if self._record_state(state, record_id) == "live"
        )
        hygiene = tuple(
            (
                HygieneOperation(
                    operation_key=operation.operation_key,
                    target_scope_id=operation.target_scope_id,
                    record_id=operation.record_id,
                    captures={
                        **operation.captures,
                        "unresolved_capable_record_count": len(
                            unresolved_capable
                        ),
                        "unresolved_live_record_count": len(unresolved_live),
                    },
                )
                if operation.operation_key == "astichi.operation.gate_no_unresolved"
                else operation
            )
            for operation in plan.hygiene_stream
        )
        return MaterializationPlan(
            root_occurrence_id=plan.root_occurrence_id,
            operation_stream=plan.operation_stream,
            hygiene_stream=hygiene,
            debug_views=plan.debug_views,
            artifact_requests=plan.artifact_requests,
        )

    def _append_package_marker_hygiene(
        self,
        state: AssemblyState,
        plan: MaterializationPlan,
    ) -> MaterializationPlan:
        hygiene: list[HygieneOperation] = []
        for occurrence in state.occurrences:
            if not occurrence.live:
                continue
            package = self._template(occurrence.template_id).package_v2
            for marker in package.markers:
                source_name = package.marker_source_name(marker)
                if source_name not in {
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
                            if source_name == "astichi_keep"
                            else "astichi.operation.strip_marker"
                        ),
                        target_scope_id=marker.scope_id,
                        captures={
                            "marker": source_name,
                            "name": package.marker_resource_name(marker),
                            "occurrence_id": occurrence.occurrence_id.index,
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

    def _unresolved_capable_records(
        self,
        state: AssemblyState,
    ) -> tuple[RecordId, ...]:
        record_ids: list[RecordId] = []
        for occurrence in state.occurrences:
            template = self._template(occurrence.template_id)
            package = template.package_v2
            for row in package.records:
                if not _is_unresolved_capable_inventory_kind(
                    package.record_inventory_kind(row)
                ):
                    continue
                template_record = template.records[row.template_record_id]
                record_ids.append(
                    RecordId(
                        occurrence_id=occurrence.occurrence_id,
                        template_record_id=template_record.template_record_id,
                    )
                )
        return tuple(record_ids)

    def _record_state(self, state: AssemblyState, record_id: RecordId) -> str:
        occurrence = state.occurrences[record_id.occurrence_id.index]
        if not occurrence.live or record_id in state.dead_records:
            return "dead"
        if record_id in state.satisfied_records:
            return "satisfied"
        return "live"

    def _defaulted_block_fallback_operations(
        self,
        state: AssemblyState,
    ) -> tuple[MaterializationOperation, ...]:
        edge_targets = {edge.target_record_id for edge in state.edges}
        fallback_records: list[tuple[int, RecordId]] = []
        for record_id in state.indexes.by_inventory_kind.get("hole.block", ()):
            if record_id in edge_targets or record_id in state.dead_records:
                continue
            occurrence = self.occurrence(state, record_id.occurrence_id)
            if not occurrence.live:
                continue
            record = self.template_record(state, record_id)
            projection = record.projection_record
            payload = getattr(projection, "payload", None)
            if not bool(getattr(payload, "has_default", False)):
                continue
            locator = self.locator_for_record(state, record_id)
            fallback_records.append((locator.ast_path.count("/"), record_id))
        return tuple(
            MaterializationOperation(
                operation_key="astichi.operation.splice_body_at_marker",
                target_record_id=record_id,
                captures={
                    "fallback_selected": True,
                    "target_state": "live",
                },
            )
            for _depth, record_id in sorted(
                fallback_records,
                key=lambda item: (
                    -item[0],
                    item[1].occurrence_id.index,
                    item[1].template_record_id.index,
                ),
            )
        )

    def _template(self, template_id: TemplateId) -> Template:
        self._check_template_id(template_id)
        return self._templates[template_id.index]

    def _check_template_id(self, template_id: TemplateId) -> None:
        self._check_owner(template_id.owner)
        if template_id.index >= len(self._templates):
            raise StaleHandleError(f"unknown template handle: {template_id.index}")

    def _check_occurrence_id(self, occurrence_id: OccurrenceId) -> None:
        self._check_owner(occurrence_id.owner)

    def _check_overlay_id(self, overlay_id: OverlayId) -> None:
        self._check_owner(overlay_id.owner)

    def _check_record_id(self, record_id: RecordId) -> None:
        self._check_owner(record_id.owner)

    def _check_state(self, state: AssemblyState) -> None:
        self._check_owner(state.owner)

    def _check_owner(self, owner: EngineOwner) -> None:
        if owner != self._owner:
            raise StaleHandleError("handle belongs to another lower engine")
