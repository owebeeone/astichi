"""Lower-engine template metadata."""

from __future__ import annotations

from dataclasses import dataclass

from astichi.lower_engine.handles import LocatorId, TemplateId, TemplateRecordId
from astichi.lower_engine.handles import SurfaceId
from astichi.lower_engine.package_v2 import LowerTemplatePackageV2


@dataclass(frozen=True, slots=True)
class TemplateRecordSpec:
    """Input spec for one template record in the skeleton engine."""

    surface_key: str
    semantic_summary: str
    ast_path: str
    role_key: str
    materialization_anchor: str
    authored_summary: str
    surface_id: SurfaceId | None = None
    resource_name: str = ""
    inventory_kind: str = ""
    code_owner_parts: tuple[str, ...] = ()
    legacy_record_id: str = ""
    projection_record: object | None = None


@dataclass(frozen=True, slots=True)
class TemplateScopeSpec:
    """Input spec for one lexical scope row in a lower template package."""

    scope_kind: str
    ast_path: str
    owner_path: tuple[str, ...]
    local_bindings: tuple[str, ...] = ()
    arguments: tuple[str, ...] = ()
    parent_scope_id: int | None = None


@dataclass(frozen=True, slots=True)
class TemplateMarkerSpec:
    """Input spec for one recognized marker row in a lower template package."""

    marker_kind: str
    source_name: str
    ast_path: str
    statement_path: str | None
    owner_path: tuple[str, ...]
    scope_id: int
    source_order: int
    resource_name: str = ""
    operation_key: str = ""
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TemplatePyImportMarkerSpec:
    """Typed source facts for one ``astichi_pyimport`` marker row."""

    marker_id: int
    module_path: tuple[str, ...] | None
    names: tuple[str, ...] = ()
    as_name: str = ""
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TemplateCommentMarkerSpec:
    """Typed source facts for one ``astichi_comment`` marker row."""

    marker_id: int
    payload: str
    flags: tuple[str, ...] = ()


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
    surface_id: SurfaceId | None = None
    resource_name: str = ""
    inventory_kind: str = ""
    code_owner_parts: tuple[str, ...] = ()
    legacy_record_id: str = ""
    projection_record: object | None = None


@dataclass(frozen=True, slots=True)
class Template:
    template_id: TemplateId
    template_key: str
    source_summary: str
    locators: tuple[SourceLocator, ...]
    records: tuple[TemplateRecord, ...]
    package_v2: LowerTemplatePackageV2
