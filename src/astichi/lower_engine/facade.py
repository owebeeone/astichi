"""Facade helpers for lower-backed composables during route-through."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from dataclasses import dataclass, field, replace
from types import ModuleType
from typing import Any

from astichi.asttools import clone_ast
from astichi.asttools.shapes import (
    BLOCK,
    ELIF_CLAUSE,
    IDENTIFIER,
    NAMED_VARIADIC,
    PARAMETER,
    POSITIONAL_VARIADIC,
    SCALAR_EXPR,
    MarkerShape,
)
from astichi.lower_engine.errors import LowerEngineError
from astichi.lower_engine.catalog import current_surface_bundle_spec
from astichi.lower_engine.engine import LowerEngine
from astichi.lower_engine.handles import TemplateId
from astichi.lower_engine.package_extract import (
    extract_comment_marker_specs,
    extract_marker_specs,
    extract_pyimport_marker_specs,
    extract_ref_marker_specs,
    extract_scope_specs,
    extract_unroll_marker_specs,
)
from astichi.lower_engine.package_v2 import (
    LowerTemplatePackageV2,
    package_from_snapshot,
)
from astichi.lower_engine.registry import RegisteredSurfaceBundle
from astichi.lower_engine.templates import (
    TemplateCommentMarkerSpec,
    TemplateMarkerSpec,
    TemplatePyImportMarkerSpec,
    TemplateRefMarkerSpec,
    TemplateRecordSpec,
    TemplateScopeSpec,
    TemplateUnrollMarkerSpec,
)
from astichi.lowering.call_argument_payloads import extract_funcargs_payload
from astichi.lowering.markers import strip_identifier_suffix
from astichi.model.composable import Composable
from astichi.model.inventory import (
    BlockProductionInventoryPayload,
    ClassCodePathNode,
    CodeNodeResourceName,
    CodePath,
    CodePathNode,
    ClauseHoleInventoryPayload,
    ExpressionProductionInventoryPayload,
    FuncargsProductionInventoryPayload,
    HoleInventoryPayload,
    Inventory,
    InventoryPayload,
    InventoryRecord,
    FunctionCodePathNode,
    MutableInventory,
    NodeLocator,
    PortInventoryPayload,
    ResourcePath,
    SourceLocation,
    StaticCodePathNode,
    StaticResourceName,
)
from astichi.model.origin import CompileOrigin
from astichi.model.ports import DemandPort, SupplyPort
from astichi.model.semantics import (
    ARG_IDENTIFIER_ORIGIN,
    BIND_EXTERNAL_ORIGIN,
    CONST_MUTABILITY,
    ELIF_PAYLOAD_ORIGIN,
    EXPORT_ORIGIN,
    HOLE_ORIGIN,
    IMPORT_ORIGIN,
    INSERT_ORIGIN,
    PARAMETER_HOLE_ORIGIN,
    PARAMETER_PAYLOAD_ORIGIN,
    PASS_ORIGIN,
    PortOrigins,
    placement_for_shape,
)


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
    pyimport_marker_specs: tuple[TemplatePyImportMarkerSpec, ...]
    comment_marker_specs: tuple[TemplateCommentMarkerSpec, ...]
    ref_marker_specs: tuple[TemplateRefMarkerSpec, ...]
    unroll_marker_specs: tuple[TemplateUnrollMarkerSpec, ...]
    surface_bundle_signature: str
    package_v2: LowerTemplatePackageV2
    backend: str = "python"
    native_snapshot: dict[str, object] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    native_package_snapshot: dict[str, object] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    native_source: str | None = field(default=None, repr=False, compare=False)
    native_origin: CompileOrigin | None = field(default=None, repr=False, compare=False)

    def has_native_lower_package(self) -> bool:
        """Return whether a native-owned lower package is attached."""
        return (
            self.backend.startswith("native-")
            and self.native_package_snapshot is not None
        )

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
    pyimport_marker_specs = extract_pyimport_marker_specs(tree)
    comment_marker_specs = extract_comment_marker_specs(tree)
    ref_marker_specs = extract_ref_marker_specs(tree)
    unroll_marker_specs = extract_unroll_marker_specs(tree)
    source_summary = _source_summary(origin=origin, record_count=len(record_specs))
    template_key = _template_key(tree=tree, source_summary=source_summary)
    template_id = engine.register_template(
        template_key=template_key,
        source_summary=source_summary,
        records=record_specs,
        scopes=scope_specs,
        markers=marker_specs,
        pyimport_markers=pyimport_marker_specs,
        comment_markers=comment_marker_specs,
        ref_markers=ref_marker_specs,
        unroll_markers=unroll_marker_specs,
    )
    return LowerTemplateBinding(
        engine=engine,
        template_id=template_id,
        template_key=template_key,
        source_summary=source_summary,
        record_specs=record_specs,
        scope_specs=scope_specs,
        marker_specs=marker_specs,
        pyimport_marker_specs=pyimport_marker_specs,
        comment_marker_specs=comment_marker_specs,
        ref_marker_specs=ref_marker_specs,
        unroll_marker_specs=unroll_marker_specs,
        surface_bundle_signature=bundle.bundle_signature,
        package_v2=engine.template_package(template_id),
    )


def register_native_template_source(
    *,
    source: str,
    origin: CompileOrigin,
    fallback_binding: LowerTemplateBinding,
) -> LowerTemplateBinding:
    """Attach native-extracted lower metadata to a binding facade."""
    from astichi.lower_engine.native import load_native_extension

    module = load_native_extension(required=True)
    assert module is not None
    native_package_snapshot = _extract_native_package_snapshot(
        module=module,
        source=source,
        origin=origin,
    )
    native_snapshot = _extract_native_template_snapshot(
        module=module,
        source=source,
        origin=origin,
    )
    native_package = package_from_snapshot(native_package_snapshot)
    native_specs = _native_specs_from_package_snapshot(
        engine=fallback_binding.engine,
        snapshot=native_package_snapshot,
        fallback_binding=fallback_binding,
        projection_records=None,
    )
    return replace(
        fallback_binding,
        backend=_native_backend_name(module),
        template_key=str(native_package_snapshot["template_key"]),
        source_summary=str(native_package_snapshot["source_summary"]),
        record_specs=native_specs.record_specs,
        scope_specs=native_specs.scope_specs,
        marker_specs=native_specs.marker_specs,
        pyimport_marker_specs=native_specs.pyimport_marker_specs,
        comment_marker_specs=native_specs.comment_marker_specs,
        ref_marker_specs=native_specs.ref_marker_specs,
        unroll_marker_specs=native_specs.unroll_marker_specs,
        surface_bundle_signature=str(
            native_package_snapshot["surface_bundle_signature"]
        ),
        package_v2=native_package,
        native_snapshot=native_snapshot,
        native_package_snapshot=native_package_snapshot,
        native_source=source,
        native_origin=origin,
    )


def register_native_template_source_direct(
    *,
    source: str,
    origin: CompileOrigin,
    tree: ast.Module,
) -> tuple[LowerTemplateBinding, Inventory]:
    """Register native-extracted lower metadata without Python inventory extraction."""
    from astichi.lower_engine.native import load_native_extension

    module = load_native_extension(required=True)
    assert module is not None
    native_package_snapshot = _extract_native_package_snapshot(
        module=module,
        source=source,
        origin=origin,
    )
    native_snapshot = _extract_native_template_snapshot(
        module=module,
        source=source,
        origin=origin,
    )
    native_package = package_from_snapshot(native_package_snapshot)
    (
        projection_inventory,
        projection_records,
    ) = _projection_inventory_from_package_snapshot(
        tree=tree,
        origin=origin,
        snapshot=native_package_snapshot,
    )
    engine = LowerEngine()
    bundle = ensure_current_surface_bundle(engine)
    native_specs = _native_specs_from_package_snapshot(
        engine=engine,
        snapshot=native_package_snapshot,
        fallback_binding=None,
        projection_records=projection_records,
    )
    template_id = engine.register_template(
        template_key=str(native_package_snapshot["template_key"]),
        source_summary=str(native_package_snapshot["source_summary"]),
        records=native_specs.record_specs,
        scopes=native_specs.scope_specs,
        markers=native_specs.marker_specs,
        pyimport_markers=native_specs.pyimport_marker_specs,
        comment_markers=native_specs.comment_marker_specs,
        ref_markers=native_specs.ref_marker_specs,
        unroll_markers=native_specs.unroll_marker_specs,
    )
    return (
        LowerTemplateBinding(
            engine=engine,
            template_id=template_id,
            template_key=str(native_package_snapshot["template_key"]),
            source_summary=str(native_package_snapshot["source_summary"]),
            record_specs=native_specs.record_specs,
            scope_specs=native_specs.scope_specs,
            marker_specs=native_specs.marker_specs,
            pyimport_marker_specs=native_specs.pyimport_marker_specs,
            comment_marker_specs=native_specs.comment_marker_specs,
            ref_marker_specs=native_specs.ref_marker_specs,
            unroll_marker_specs=native_specs.unroll_marker_specs,
            surface_bundle_signature=bundle.bundle_signature,
            package_v2=native_package,
            backend=_native_backend_name(module),
            native_snapshot=native_snapshot,
            native_package_snapshot=native_package_snapshot,
            native_source=source,
            native_origin=origin,
        ),
        projection_inventory,
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
        cache_key = (
            binding.backend,
            binding.surface_bundle_signature,
            binding.template_key,
        )
        cached = self._template_handles_by_key.get(cache_key)
        if cached is not None:
            return cached
        if binding.native_source is not None and binding.native_origin is not None:
            handle = self.module.register_template_package_v2_source(
                self.engine_handle,
                binding.native_source,
                binding.native_origin.file_name,
                binding.native_origin.line_number,
            )
        else:
            if binding.native_snapshot is None:
                raise TypeError("binding does not carry native template metadata")
            handle = self.module.register_template_snapshot(
                self.engine_handle,
                deepcopy(binding.native_snapshot),
            )
        self._template_handles_by_key[cache_key] = handle
        return handle


@dataclass(frozen=True, slots=True)
class _NativePackageSpecs:
    record_specs: tuple[TemplateRecordSpec, ...]
    scope_specs: tuple[TemplateScopeSpec, ...]
    marker_specs: tuple[TemplateMarkerSpec, ...]
    pyimport_marker_specs: tuple[TemplatePyImportMarkerSpec, ...]
    comment_marker_specs: tuple[TemplateCommentMarkerSpec, ...]
    ref_marker_specs: tuple[TemplateRefMarkerSpec, ...]
    unroll_marker_specs: tuple[TemplateUnrollMarkerSpec, ...]


def _native_specs_from_package_snapshot(
    *,
    engine: LowerEngine,
    snapshot: dict[str, object],
    fallback_binding: LowerTemplateBinding | None,
    projection_records: tuple[InventoryRecord, ...] | None,
) -> _NativePackageSpecs:
    ensure_current_surface_bundle(engine)
    locator_rows = {
        int(row["locator_id"]): row
        for row in _snapshot_rows(snapshot, "locators")
    }
    fallback_records = (
        () if fallback_binding is None else fallback_binding.record_specs
    )
    record_specs: list[TemplateRecordSpec] = []
    for index, row in enumerate(_snapshot_rows(snapshot, "records")):
        locator = locator_rows[int(row["locator_id"])]
        fallback = fallback_records[index] if index < len(fallback_records) else None
        projection_record = (
            None
            if projection_records is None or index >= len(projection_records)
            else projection_records[index]
        )
        legacy_record_id = "" if fallback is None else fallback.legacy_record_id
        template_projection = (
            None if fallback is None else fallback.projection_record
        )
        if projection_record is not None:
            legacy_record_id = projection_record.record_id
            template_projection = projection_record
        surface_key = _row_string(row, "surface_key")
        record_specs.append(
            TemplateRecordSpec(
                surface_key=surface_key,
                semantic_summary=_row_string(row, "semantic_summary"),
                ast_path=_row_string(locator, "ast_path"),
                role_key=_row_string(locator, "role_key"),
                materialization_anchor=_row_string(
                    locator,
                    "materialization_anchor",
                ),
                authored_summary=_row_string(locator, "authored_summary"),
                surface_id=engine.surface_registry.surface_handle(surface_key),
                resource_name=_row_string(row, "resource_name"),
                inventory_kind=_row_string(row, "inventory_kind"),
                code_owner_parts=_row_string_tuple(row, "owner_path"),
                legacy_record_id=legacy_record_id,
                projection_record=template_projection,
            )
        )
    return _NativePackageSpecs(
        record_specs=tuple(record_specs),
        scope_specs=tuple(
            TemplateScopeSpec(
                scope_kind=_row_string(row, "scope_kind"),
                ast_path=_row_string(row, "ast_path"),
                owner_path=_row_string_tuple(row, "owner_path"),
                local_bindings=_row_string_tuple(row, "local_bindings"),
                arguments=_row_string_tuple(row, "arguments"),
                parent_scope_id=(
                    None
                    if row["parent_scope_id"] is None
                    else int(row["parent_scope_id"])
                ),
            )
            for row in _snapshot_rows(snapshot, "scopes")
        ),
        marker_specs=tuple(
            TemplateMarkerSpec(
                marker_kind=_row_string(row, "marker_kind"),
                source_name=_row_string(row, "source_name"),
                ast_path=_row_string(row, "ast_path"),
                statement_path=(
                    None
                    if row["statement_path"] is None
                    else _row_string(row, "statement_path")
                ),
                owner_path=_row_string_tuple(row, "owner_path"),
                scope_id=int(row["scope_id"]),
                source_order=int(row["source_order"]),
                resource_name=_row_string(row, "resource_name"),
                operation_key=_row_string(row, "operation_key"),
                flags=_row_string_tuple(row, "flags"),
            )
            for row in _snapshot_rows(snapshot, "markers")
        ),
        pyimport_marker_specs=tuple(
            TemplatePyImportMarkerSpec(
                marker_id=int(row["marker_id"]),
                module_path=(
                    None
                    if row["module_path"] is None
                    else _row_string_tuple(row, "module_path")
                ),
                names=_row_string_tuple(row, "names"),
                as_name=_row_string(row, "as_name"),
                flags=_row_string_tuple(row, "flags"),
            )
            for row in _snapshot_rows(snapshot, "pyimport_markers")
        ),
        comment_marker_specs=tuple(
            TemplateCommentMarkerSpec(
                marker_id=int(row["marker_id"]),
                payload=_row_string(row, "payload"),
                flags=_row_string_tuple(row, "flags"),
            )
            for row in _snapshot_rows(snapshot, "comment_markers")
        ),
        ref_marker_specs=tuple(
            TemplateRefMarkerSpec(
                marker_id=int(row["marker_id"]),
                ref_kind=_row_string(row, "ref_kind"),
                context=_row_string(row, "context"),
                sentinel_attr=_row_string(row, "sentinel_attr"),
                literal_path=(
                    None
                    if row["literal_path"] is None
                    else _row_string_tuple(row, "literal_path")
                ),
                flags=_row_string_tuple(row, "flags"),
            )
            for row in _snapshot_rows(snapshot, "ref_markers")
        ),
        unroll_marker_specs=tuple(
            TemplateUnrollMarkerSpec(
                marker_id=int(row["marker_id"]),
                statement_path=_row_string(row, "statement_path"),
                target_ast_path=_row_string(row, "target_ast_path"),
                iter_ast_path=_row_string(row, "iter_ast_path"),
                domain_ast_path=_row_string(row, "domain_ast_path"),
                body_path=_row_string(row, "body_path"),
                orelse_path=(
                    None
                    if row["orelse_path"] is None
                    else _row_string(row, "orelse_path")
                ),
                target_bindings=_row_string_tuple(row, "target_bindings"),
                domain_shape=_row_string(row, "domain_shape"),
                flags=_row_string_tuple(row, "flags"),
            )
            for row in _snapshot_rows(snapshot, "unroll_markers")
        ),
    )


def _snapshot_rows(
    snapshot: dict[str, object],
    section: str,
) -> tuple[dict[str, object], ...]:
    rows = snapshot[section]
    if not isinstance(rows, list):
        raise TypeError(f"native package section {section!r} must be a list")
    if not all(isinstance(row, dict) for row in rows):
        raise TypeError(f"native package section {section!r} must contain rows")
    return tuple(rows)


def _row_string(row: dict[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"native package row field {key!r} must be a string")
    return value


def _row_string_tuple(row: dict[str, object], key: str) -> tuple[str, ...]:
    value = row[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise TypeError(f"native package row field {key!r} must be a string list")
    return tuple(value)


def _projection_inventory_from_package_snapshot(
    *,
    tree: ast.Module,
    origin: CompileOrigin,
    snapshot: dict[str, object],
) -> tuple[Inventory, tuple[InventoryRecord, ...]]:
    locator_rows = {
        int(row["locator_id"]): row
        for row in _snapshot_rows(snapshot, "locators")
    }
    marker_rows = {
        (_row_string(row, "ast_path"), _row_string(row, "resource_name")): row
        for row in _snapshot_rows(snapshot, "markers")
    }
    marker_rows_by_path = {
        _row_string(row, "ast_path"): row
        for row in _snapshot_rows(snapshot, "markers")
    }
    mutable = MutableInventory()
    records: list[InventoryRecord] = []
    for row in _snapshot_rows(snapshot, "records"):
        template_record_id = int(row["template_record_id"])
        locator = locator_rows[int(row["locator_id"])]
        ast_path = _row_string(locator, "ast_path")
        node = _ast_node_at_path(tree, ast_path)
        record = InventoryRecord(
            record_id=f"#{template_record_id + 1}",
            build_path=ResourcePath(),
            code_owner=_code_path_for_owner_path(
                tree,
                _row_string_tuple(row, "owner_path"),
            ),
            name=_projection_resource_name(row, node),
            kind=_row_string(row, "inventory_kind"),
            locator=_node_locator_from_ast_path(ast_path),
            payload=_projection_payload_for_native_record(
                row,
                node,
                marker=_marker_for_projection_record(
                    marker_rows,
                    marker_rows_by_path,
                    ast_path=ast_path,
                    resource_name=_row_string(row, "resource_name"),
                ),
            ),
            source_location=_source_location_for_projection(
                node,
                origin=origin,
                authored_summary=_row_string(locator, "authored_summary"),
            ),
        )
        mutable.add_existing_record(record)
        records.append(record)
    return mutable.freeze(), tuple(records)


def _marker_for_projection_record(
    marker_rows: dict[tuple[str, str], dict[str, object]],
    marker_rows_by_path: dict[str, dict[str, object]],
    *,
    ast_path: str,
    resource_name: str,
) -> dict[str, object] | None:
    return marker_rows.get((ast_path, resource_name)) or marker_rows_by_path.get(
        ast_path
    )


def _projection_resource_name(
    row: dict[str, object],
    node: ast.AST | None,
):
    if isinstance(node, ast.ClassDef):
        return CodeNodeResourceName(ClassCodePathNode(node))
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return CodeNodeResourceName(FunctionCodePathNode(node))
    return StaticResourceName(_row_string(row, "resource_name"))


def _code_path_for_owner_path(
    tree: ast.Module,
    owner_path: tuple[str, ...],
) -> CodePath:
    body: list[ast.stmt] = list(tree.body)
    nodes: list[CodePathNode] = []
    for part in owner_path:
        matched = _find_owner_node(body, part)
        if matched is None:
            nodes.append(StaticCodePathNode(part))
            body = []
            continue
        if isinstance(matched, ast.ClassDef):
            nodes.append(ClassCodePathNode(matched))
            body = list(matched.body)
            continue
        nodes.append(FunctionCodePathNode(matched))
        body = list(matched.body)
    return CodePath(tuple(nodes))


def _find_owner_node(
    body: list[ast.stmt],
    logical_name: str,
) -> ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef | None:
    for statement in body:
        if not isinstance(
            statement,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        stripped, _ = strip_identifier_suffix(statement.name)
        if stripped == logical_name:
            return statement
    return None


def _projection_payload_for_native_record(
    row: dict[str, object],
    node: ast.AST | None,
    *,
    marker: dict[str, object] | None,
) -> InventoryPayload:
    surface_key = _row_string(row, "surface_key")
    kind = _row_string(row, "inventory_kind")
    name = _row_string(row, "resource_name")
    if kind.startswith("hole."):
        port = _native_demand_port(name, _shape_for_hole_kind(kind), HOLE_ORIGIN)
        if kind == "hole.elif":
            return ClauseHoleInventoryPayload(port=port)
        if kind == "hole.params":
            return HoleInventoryPayload(
                port=_native_demand_port(name, PARAMETER, PARAMETER_HOLE_ORIGIN)
            )
        return HoleInventoryPayload(
            port=port,
            has_default=kind == "hole.block" and isinstance(node, ast.With),
        )
    if kind == "external.bind":
        return PortInventoryPayload(
            _native_demand_port(name, SCALAR_EXPR, BIND_EXTERNAL_ORIGIN)
        )
    if kind == "identifier.demand":
        return PortInventoryPayload(
            _native_demand_port(
                name,
                IDENTIFIER,
                _identifier_demand_origin(marker),
            )
        )
    if kind == "identifier.supply":
        return PortInventoryPayload(
            _native_supply_port(name, SCALAR_EXPR, EXPORT_ORIGIN)
        )
    if kind == "production.block":
        return BlockProductionInventoryPayload()
    if kind == "production.expression":
        if not isinstance(node, ast.expr):
            raise TypeError(
                "native expression production locator must resolve to ast.expr"
            )
        return ExpressionProductionInventoryPayload(node)
    if kind == "production.funcargs":
        if not isinstance(node, ast.Call):
            raise TypeError(
                "native funcargs production locator must resolve to ast.Call"
            )
        payload = extract_funcargs_payload(node)
        if payload is None:
            raise TypeError("native funcargs production locator is not astichi_funcargs")
        return FuncargsProductionInventoryPayload(payload)
    if kind == "production.elif":
        return PortInventoryPayload(
            _native_supply_port(name, ELIF_CLAUSE, ELIF_PAYLOAD_ORIGIN)
        )
    if kind == "production.supply":
        if surface_key == "astichi.surface.parameter.production":
            return PortInventoryPayload(
                _native_supply_port(name, PARAMETER, PARAMETER_PAYLOAD_ORIGIN)
            )
        return PortInventoryPayload(
            _native_supply_port(name, SCALAR_EXPR, INSERT_ORIGIN)
        )
    raise TypeError(f"unsupported native projection inventory kind: {kind}")


def _identifier_demand_origin(marker: dict[str, object] | None):
    if marker is None:
        return ARG_IDENTIFIER_ORIGIN
    source_name = _row_string(marker, "source_name")
    if source_name == "astichi_import":
        return IMPORT_ORIGIN
    if source_name == "astichi_pass":
        return PASS_ORIGIN
    return ARG_IDENTIFIER_ORIGIN


def _native_demand_port(
    name: str,
    shape: MarkerShape,
    origin,
) -> DemandPort:
    return DemandPort(
        name=name,
        shape=shape,
        placement=placement_for_shape(shape),
        mutability=CONST_MUTABILITY,
        origins=PortOrigins.of(origin),
    )


def _native_supply_port(
    name: str,
    shape: MarkerShape,
    origin,
) -> SupplyPort:
    return SupplyPort(
        name=name,
        shape=shape,
        placement=placement_for_shape(shape),
        mutability=CONST_MUTABILITY,
        origins=PortOrigins.of(origin),
    )


def _shape_for_hole_kind(kind: str) -> MarkerShape:
    if kind == "hole.expr":
        return SCALAR_EXPR
    if kind == "hole.block":
        return BLOCK
    if kind == "hole.params":
        return PARAMETER
    if kind == "hole.elif":
        return ELIF_CLAUSE
    if kind == "hole.positional_variadic":
        return POSITIONAL_VARIADIC
    if kind == "hole.named_variadic":
        return NAMED_VARIADIC
    raise TypeError(f"unsupported native hole inventory kind: {kind}")


def _node_locator_from_ast_path(ast_path: str) -> NodeLocator:
    if ast_path in {"", "."}:
        return NodeLocator()
    return NodeLocator(tuple(ast_path.split("/")))


def _ast_node_at_path(tree: ast.Module, ast_path: str) -> ast.AST | None:
    node: object = tree
    if ast_path in {"", "."}:
        return tree
    for segment in ast_path.split("/"):
        if not isinstance(node, ast.AST):
            return None
        field_name, index = _parse_ast_path_segment(segment)
        value = getattr(node, field_name, None)
        if index is None:
            node = value
            continue
        if not isinstance(value, list) or index >= len(value):
            return None
        node = value[index]
    return node if isinstance(node, ast.AST) else None


def _parse_ast_path_segment(segment: str) -> tuple[str, int | None]:
    if segment.endswith("]") and "[" in segment:
        field_name, raw_index = segment[:-1].rsplit("[", 1)
        return field_name, int(raw_index)
    return segment, None


def _source_location_for_projection(
    node: ast.AST | None,
    *,
    origin: CompileOrigin,
    authored_summary: str,
) -> SourceLocation | None:
    line_number = getattr(node, "lineno", None)
    if not isinstance(line_number, int):
        line_number = _line_number_from_authored_summary(authored_summary)
    if not isinstance(line_number, int):
        return None
    return SourceLocation(file_name=origin.file_name, line_number=line_number)


def _line_number_from_authored_summary(summary: str) -> int | None:
    marker = " at line "
    if marker not in summary:
        return None
    tail = summary.rsplit(marker, 1)[1]
    digits = []
    for char in tail:
        if not char.isdigit():
            break
        digits.append(char)
    if not digits:
        return None
    return int("".join(digits))


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


def _extract_native_package_snapshot(
    *,
    module: ModuleType,
    source: str,
    origin: CompileOrigin,
) -> dict[str, object]:
    bundle_snapshot = _current_surface_bundle_snapshot()
    handle = module.engine_create()
    try:
        module.register_surface_bundle(handle, deepcopy(bundle_snapshot))
        snapshot = module.extract_template_package_v2_snapshot(
            handle,
            source,
            origin.file_name,
            origin.line_number,
        )
    finally:
        module.engine_close(handle)
    if not isinstance(snapshot, dict):
        raise TypeError("native package snapshot must be a dict")
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
        pyimport_markers=binding.pyimport_marker_specs,
        comment_markers=binding.comment_marker_specs,
        ref_markers=binding.ref_marker_specs,
        unroll_markers=binding.unroll_marker_specs,
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
