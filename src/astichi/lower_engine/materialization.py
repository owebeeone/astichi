"""Lower-engine materialization plan data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from astichi.lower_engine.handles import OccurrenceId, OverlayId, RecordId


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
