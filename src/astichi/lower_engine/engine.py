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
from astichi.lower_engine.materialization import MaterializationPlan
from astichi.lower_engine.registry import SurfaceRegistry
from astichi.lower_engine.snapshots import structural_snapshot
from astichi.lower_engine.templates import (
    SourceLocator,
    Template,
    TemplateRecord,
    TemplateRecordSpec,
)

_OWNER_IDS = count()


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
    ) -> TemplateId:
        """Register immutable template metadata and return its handle."""
        template_id = TemplateId(owner=self._owner, index=len(self._templates))
        locators: list[SourceLocator] = []
        template_records: list[TemplateRecord] = []
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
                )
            )
        self._templates.append(
            Template(
                template_id=template_id,
                template_key=template_key,
                source_summary=source_summary,
                locators=tuple(locators),
                records=tuple(template_records),
            )
        )
        return template_id

    def new_state(self) -> AssemblyState:
        """Create a mutable assembly state owned by this engine."""
        return AssemblyState(owner=self._owner, owner_label=self._owner_label)

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
