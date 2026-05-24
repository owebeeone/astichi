"""Lower-engine assembly state tables."""

from __future__ import annotations

from dataclasses import dataclass, field

from astichi.lower_engine.handles import (
    EdgeId,
    EngineOwner,
    OccurrenceId,
    OverlayId,
    RecordId,
    TemplateId,
)


@dataclass(frozen=True, slots=True)
class Occurrence:
    occurrence_id: OccurrenceId
    template_id: TemplateId
    build_path: tuple[str, ...]
    parent_occurrence_id: OccurrenceId | None = None
    overlay_id: OverlayId | None = None
    live: bool = True


@dataclass(frozen=True, slots=True)
class AssemblyEdge:
    edge_id: EdgeId
    target_record_id: RecordId
    source_occurrence_id: OccurrenceId
    operation_key: str
    order: int


@dataclass(frozen=True, slots=True)
class Overlay:
    overlay_id: OverlayId
    kind: str
    source_label: str
    target_record_id: RecordId


@dataclass(slots=True)
class InventoryIndexes:
    by_build_path: dict[tuple[str, ...], list[RecordId]] = field(default_factory=dict)
    by_surface: dict[str, list[RecordId]] = field(default_factory=dict)

    def append(self, *, build_path: tuple[str, ...], surface_key: str, record_id: RecordId) -> None:
        self.by_build_path.setdefault(build_path, []).append(record_id)
        self.by_surface.setdefault(surface_key, []).append(record_id)


@dataclass(slots=True)
class AssemblyState:
    owner: EngineOwner
    owner_label: str
    occurrences: list[Occurrence] = field(default_factory=list)
    edges: list[AssemblyEdge] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    satisfied_records: set[RecordId] = field(default_factory=set)
    dead_records: set[RecordId] = field(default_factory=set)
    indexes: InventoryIndexes = field(default_factory=InventoryIndexes)
