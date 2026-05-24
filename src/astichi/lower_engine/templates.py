"""Lower-engine template metadata."""

from __future__ import annotations

from dataclasses import dataclass

from astichi.lower_engine.handles import LocatorId, TemplateId, TemplateRecordId


@dataclass(frozen=True, slots=True)
class TemplateRecordSpec:
    """Input spec for one template record in the skeleton engine."""

    surface_key: str
    semantic_summary: str
    ast_path: str
    role_key: str
    materialization_anchor: str
    authored_summary: str


@dataclass(frozen=True, slots=True)
class SourceLocator:
    locator_id: LocatorId
    template_id: TemplateId
    ast_path: str
    role_key: str
    parent_locator_id: LocatorId | None
    authored_summary: str
    materialization_anchor: str


@dataclass(frozen=True, slots=True)
class TemplateRecord:
    template_record_id: TemplateRecordId
    surface_key: str
    semantic_summary: str
    locator_id: LocatorId


@dataclass(frozen=True, slots=True)
class Template:
    template_id: TemplateId
    template_key: str
    source_summary: str
    locators: tuple[SourceLocator, ...]
    records: tuple[TemplateRecord, ...]
