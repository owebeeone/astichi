"""Owned lower-engine handles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EngineOwner:
    """Private owner token for handles created by one engine instance."""

    owner_id: int


@dataclass(frozen=True, slots=True)
class TemplateId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class TemplateRecordId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class LocatorId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class OccurrenceId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class EdgeId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class OverlayId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class SurfaceId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class OperationId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class PatternId:
    owner: EngineOwner
    index: int


@dataclass(frozen=True, slots=True)
class RecordId:
    occurrence_id: OccurrenceId
    template_record_id: TemplateRecordId

    @property
    def owner(self) -> EngineOwner:
        """Return the common owner for this derived record handle."""
        return self.occurrence_id.owner

    def __post_init__(self) -> None:
        if self.occurrence_id.owner != self.template_record_id.owner:
            raise ValueError("record id handles must share an engine owner")
