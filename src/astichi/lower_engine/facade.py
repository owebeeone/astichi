"""Facade helpers for lower-backed composables during route-through."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from dataclasses import dataclass, field, replace
from types import ModuleType
from typing import Any

from astichi.asttools import clone_ast
from astichi.lower_engine.errors import LowerEngineError
from astichi.lower_engine.catalog import current_surface_bundle_spec
from astichi.lower_engine.engine import LowerEngine
from astichi.lower_engine.handles import TemplateId
from astichi.lower_engine.package_extract import extract_marker_specs, extract_scope_specs
from astichi.lower_engine.package_v2 import LowerTemplatePackageV2
from astichi.lower_engine.registry import RegisteredSurfaceBundle
from astichi.lower_engine.templates import (
    TemplateMarkerSpec,
    TemplateRecordSpec,
    TemplateScopeSpec,
)
from astichi.model.composable import Composable
from astichi.model.inventory import (
    BlockProductionInventoryPayload,
    ClauseHoleInventoryPayload,
    ExpressionProductionInventoryPayload,
    FuncargsProductionInventoryPayload,
    HoleInventoryPayload,
    Inventory,
    InventoryRecord,
    PortInventoryPayload,
)
from astichi.model.origin import CompileOrigin
from astichi.model.ports import DemandPort, SupplyPort


@dataclass(frozen=True, slots=True)
class LowerTemplateBinding:
    """Internal link between a Python facade composable and lower metadata."""

    engine: LowerEngine = field(repr=False, compare=False)
    template_id: TemplateId
    template_key: str
    source_summary: str
    record_specs: tuple[TemplateRecordSpec, ...]
    scope_specs: tuple[TemplateScopeSpec, ...]
    marker_specs: tuple[TemplateMarkerSpec, ...]
    surface_bundle_signature: str
    package_v2: LowerTemplatePackageV2
    backend: str = "python"
    native_snapshot: dict[str, object] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    native_source: str | None = field(default=None, repr=False, compare=False)
    native_origin: CompileOrigin | None = field(default=None, repr=False, compare=False)

    def structural_snapshot(self) -> dict[str, object]:
        """Return a deterministic structural snapshot for this template."""
        if self.native_snapshot is not None:
            return deepcopy(self.native_snapshot)
        state = self.engine.new_state()
        self.engine.append_occurrence(
            state,
            self.template_id,
            build_path=("Template",),
        )
        return self.engine.structural_snapshot(state)


def register_inventory_template(
    *,
    tree: ast.Module,
    origin: CompileOrigin,
    inventory: Inventory,
) -> LowerTemplateBinding:
    """Register existing inventory metadata as one lower-engine template."""
    engine = LowerEngine()
    bundle = engine.surface_registry.register_bundle(current_surface_bundle_spec())
    record_specs = tuple(
        _template_record_spec(engine=engine, record=record)
        for record in _sorted_inventory_records(inventory)
    )
    scope_specs = extract_scope_specs(tree)
    marker_specs = extract_marker_specs(tree, scope_specs)
    source_summary = _source_summary(origin=origin, record_count=len(record_specs))
    template_key = _template_key(tree=tree, source_summary=source_summary)
    template_id = engine.register_template(
        template_key=template_key,
        source_summary=source_summary,
        records=record_specs,
        scopes=scope_specs,
        markers=marker_specs,
    )
    return LowerTemplateBinding(
        engine=engine,
        template_id=template_id,
        template_key=template_key,
        source_summary=source_summary,
        record_specs=record_specs,
        scope_specs=scope_specs,
        marker_specs=marker_specs,
        surface_bundle_signature=bundle.bundle_signature,
        package_v2=engine.template_package(template_id),
    )


def register_native_template_source(
    *,
    source: str,
    origin: CompileOrigin,
    fallback_binding: LowerTemplateBinding,
) -> LowerTemplateBinding:
    """Attach a native-extracted structural template snapshot to a binding."""
    from astichi.lower_engine.native import load_native_extension

    module = load_native_extension(required=True)
    assert module is not None
    native_snapshot = _extract_native_template_snapshot(
        module=module,
        source=source,
        origin=origin,
    )
    return replace(
        fallback_binding,
        backend=_native_backend_name(module),
        native_snapshot=native_snapshot,
        native_source=source,
        native_origin=origin,
    )


@dataclass(slots=True)
class LowerTemplateCache:
    """Register lower template bindings once in one destination engine."""

    engine: LowerEngine
    _template_ids_by_key: dict[str, TemplateId] = field(default_factory=dict)

    def template_id_for(self, binding: LowerTemplateBinding) -> TemplateId:
        """Return the destination-engine template id for ``binding``."""
        cached = self._template_ids_by_key.get(binding.template_key)
        if cached is not None:
            return cached
        template_id = register_lower_template_binding(
            self.engine,
            binding,
        )
        self._template_ids_by_key[binding.template_key] = template_id
        return template_id


@dataclass(slots=True)
class NativeTemplateCache:
    """Register native template bindings once in one native engine handle."""

    module: ModuleType
    engine_handle: object
    _template_handles_by_key: dict[tuple[str, str, str], object] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        ensure_current_native_surface_bundle(
            module=self.module,
            engine_handle=self.engine_handle,
        )

    def template_handle_for(self, binding: LowerTemplateBinding) -> object:
        """Return the destination native template handle for ``binding``."""
        if binding.native_snapshot is None:
            raise TypeError("binding does not carry a native template snapshot")
        cache_key = (
            binding.backend,
            binding.surface_bundle_signature,
            binding.template_key,
        )
        cached = self._template_handles_by_key.get(cache_key)
        if cached is not None:
            return cached
        handle = self.module.register_template_snapshot(
            self.engine_handle,
            deepcopy(binding.native_snapshot),
        )
        self._template_handles_by_key[cache_key] = handle
        return handle


def ensure_current_native_surface_bundle(
    *,
    module: ModuleType,
    engine_handle: object,
) -> dict[str, object]:
    """Ensure one native engine handle has the current surface bundle."""
    expected = _current_surface_bundle_snapshot()
    engine_snapshot = module.engine_snapshot(engine_handle)
    if bool(engine_snapshot.get("surface_bundle_registered", False)):
        actual = module.surface_bundle_snapshot(engine_handle)
        if actual != expected:
            raise LowerEngineError("native engine has incompatible surface bundle")
        return _dict_copy(actual, "native surface bundle snapshot")
    actual = module.register_surface_bundle(
        engine_handle,
        deepcopy(expected),
    )
    return _dict_copy(actual, "native surface bundle snapshot")


def ensure_current_surface_bundle(engine: LowerEngine) -> RegisteredSurfaceBundle:
    """Ensure ``engine`` has the current Astichi surface bundle registered."""
    current = current_surface_bundle_spec()
    existing = engine.surface_registry.bundle
    if existing is None:
        return engine.surface_registry.register_bundle(current)
    if existing.bundle_key != current.bundle_key:
        raise LowerEngineError(
            f"lower engine has incompatible surface bundle: {existing.bundle_key}"
        )
    return existing


def _extract_native_template_snapshot(
    *,
    module: ModuleType,
    source: str,
    origin: CompileOrigin,
) -> dict[str, object]:
    engine = LowerEngine()
    bundle_snapshot = engine.surface_registry.register_bundle(
        current_surface_bundle_spec()
    ).snapshot()
    handle = module.engine_create()
    try:
        module.register_surface_bundle(handle, deepcopy(bundle_snapshot))
        snapshot = module.extract_template_snapshot(
            handle,
            source,
            origin.file_name,
            origin.line_number,
        )
    finally:
        module.engine_close(handle)
    if not isinstance(snapshot, dict):
        raise TypeError("native template snapshot must be a dict")
    return snapshot


def _current_surface_bundle_snapshot() -> dict[str, object]:
    engine = LowerEngine()
    bundle = engine.surface_registry.register_bundle(current_surface_bundle_spec())
    return bundle.snapshot()


def _dict_copy(value: Any, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a dict")
    return dict(value)


def _native_backend_name(module: ModuleType) -> str:
    capabilities = module.capabilities()
    label = str(capabilities.get("backend_label", ""))
    if "cpp" in label or "c++" in label:
        return "native-cpp"
    return "native-rust"


def register_lower_template_binding(
    engine: LowerEngine,
    binding: LowerTemplateBinding,
) -> TemplateId:
    """Import one compiled template binding into ``engine``."""
    ensure_current_surface_bundle(engine)
    rebound_specs = tuple(
        replace(
            spec,
            surface_id=engine.surface_registry.surface_handle(spec.surface_key),
        )
        for spec in binding.record_specs
    )
    template_id = engine.register_template(
        template_key=binding.template_key,
        source_summary=binding.source_summary,
        records=rebound_specs,
        scopes=binding.scope_specs,
        markers=binding.marker_specs,
    )
    return template_id


def copy_template_ast(tree: ast.Module) -> ast.Module:
    """Return a caller-owned copy of a template's CPython AST artifact."""
    return clone_ast(tree)


def copy_composable_template_ast(composable: Composable) -> ast.Module:
    """Return a caller-owned copy of a composable's template AST artifact."""
    tree = getattr(composable, "tree", None)
    if not isinstance(tree, ast.Module):
        raise TypeError("composable does not expose a CPython template AST")
    return copy_template_ast(tree)


def render_composable_source(
    composable: Composable,
    *,
    provenance: bool = True,
) -> str:
    """Render source through the explicit facade artifact boundary."""
    return composable.emit(provenance=provenance)


def copy_composable_executable_ast(composable: Composable) -> ast.Module:
    """Return a caller-owned executable AST through the facade boundary."""
    executable = composable.to_executable_ast()
    if not isinstance(executable, ast.Module):
        raise TypeError("composable executable artifact is not an ast.Module")
    return executable


def _template_record_spec(
    *,
    engine: LowerEngine,
    record: InventoryRecord,
) -> TemplateRecordSpec:
    surface = _surface_mapping_for(record)
    surface_id = engine.surface_registry.surface_handle(surface.surface_key)
    return TemplateRecordSpec(
        surface_key=surface.surface_key,
        semantic_summary=_semantic_summary(record),
        ast_path=str(record.locator),
        role_key=record.kind,
        materialization_anchor=surface.materialization_anchor,
        authored_summary=_authored_summary(record),
        surface_id=surface_id,
        resource_name=record.name.logical_name(),
        inventory_kind=record.kind,
        code_owner_parts=_code_owner_parts(record),
        legacy_record_id=record.record_id,
        projection_record=record,
    )


@dataclass(frozen=True, slots=True)
class _InventorySurfaceMapping:
    surface_key: str
    materialization_anchor: str


def _surface_mapping_for(record: InventoryRecord) -> _InventorySurfaceMapping:
    payload = record.payload
    if isinstance(payload, ClauseHoleInventoryPayload):
        return _InventorySurfaceMapping(
            "astichi.surface.elif.target",
            "append-clause",
        )
    if isinstance(payload, HoleInventoryPayload):
        return _hole_surface_mapping(payload.port)
    if isinstance(payload, PortInventoryPayload):
        port = payload.port
        if isinstance(port, DemandPort):
            return _demand_surface_mapping(port)
        if isinstance(port, SupplyPort):
            return _supply_surface_mapping(port)
    if isinstance(payload, FuncargsProductionInventoryPayload):
        return _InventorySurfaceMapping(
            "astichi.surface.funcargs.production",
            "copy-call-arguments",
        )
    if isinstance(payload, ExpressionProductionInventoryPayload):
        return _InventorySurfaceMapping(
            "astichi.surface.expression.production",
            "copy-expression",
        )
    if isinstance(payload, BlockProductionInventoryPayload):
        return _InventorySurfaceMapping(
            "astichi.surface.block.production",
            "copy-block",
        )
    raise TypeError(
        f"unsupported inventory payload for lower template: {type(payload).__name__}"
    )


def _hole_surface_mapping(port: DemandPort) -> _InventorySurfaceMapping:
    if port.is_parameter_hole_demand():
        return _InventorySurfaceMapping(
            "astichi.surface.parameter.hole",
            "splice-parameters",
        )
    if port.shape.is_block():
        return _InventorySurfaceMapping(
            "astichi.surface.block.hole",
            "splice-body-at-marker",
        )
    if port.shape.is_scalar_expr():
        return _InventorySurfaceMapping(
            "astichi.surface.expression.hole",
            "replace-expression",
        )
    if port.shape.is_positional_variadic() or port.shape.is_named_variadic():
        return _InventorySurfaceMapping(
            "astichi.surface.funcargs.hole",
            "splice-call-arguments",
        )
    raise TypeError(f"unsupported hole shape for lower template: {port.shape.name}")


def _demand_surface_mapping(port: DemandPort) -> _InventorySurfaceMapping:
    if port.is_external_bind_demand():
        return _InventorySurfaceMapping(
            "astichi.surface.external.demand",
            "bind-external",
        )
    if port.is_identifier_demand():
        return _InventorySurfaceMapping(
            "astichi.surface.identifier.demand",
            "rewrite-identifier",
        )
    if port.is_additive_hole_demand() or port.is_parameter_hole_demand():
        return _hole_surface_mapping(port)
    raise TypeError(f"unsupported demand port for lower template: {port.name}")


def _supply_surface_mapping(port: SupplyPort) -> _InventorySurfaceMapping:
    if port.origins.is_identifier_supply():
        return _InventorySurfaceMapping(
            "astichi.surface.identifier.supply",
            "rewrite-identifier",
        )
    if port.shape.is_elif_clause():
        return _InventorySurfaceMapping(
            "astichi.surface.elif.production",
            "copy-clause",
        )
    if port.is_signature_parameter_supply():
        return _InventorySurfaceMapping(
            "astichi.surface.parameter.production",
            "copy-parameters",
        )
    if port.is_expression_family_supply():
        return _InventorySurfaceMapping(
            "astichi.surface.expression.production",
            "copy-expression",
        )
    raise TypeError(f"unsupported supply port for lower template: {port.name}")


def _semantic_summary(record: InventoryRecord) -> str:
    return (
        f"{record.kind} name={record.name.logical_name()} "
        f"owner={record.code_owner} build_path={record.build_path}"
    )


def _code_owner_parts(record: InventoryRecord) -> tuple[str, ...]:
    return tuple(node.logical_name() for node in record.code_owner.nodes)


def _authored_summary(record: InventoryRecord) -> str:
    location = record.source_location
    location_summary = (
        f"line {location.line_number}" if location is not None else "line ?"
    )
    return f"{record.name.logical_name()} at {location_summary}"


def _source_summary(*, origin: CompileOrigin, record_count: int) -> str:
    return f"compile line={origin.line_number} records={record_count}"


def _template_key(*, tree: ast.Module, source_summary: str) -> str:
    payload = ast.dump(tree, include_attributes=False) + "\n" + source_summary
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"template:{digest}"


def _sorted_inventory_records(inventory: Inventory) -> tuple[InventoryRecord, ...]:
    return inventory.records_for_ids(tuple(inventory.records))
