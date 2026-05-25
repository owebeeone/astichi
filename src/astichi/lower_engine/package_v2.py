"""Lower template package v2 containers and snapshot projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
import re
from typing import Any

SCHEMA = "astichi.lower-template-package.v2"

SECTION_KEYS: tuple[str, ...] = (
    "schema",
    "surface_bundle_signature",
    "template_key",
    "source_summary",
    "string_table",
    "path_table",
    "ast_path_table",
    "binding_sets",
    "locators",
    "records",
    "scopes",
    "markers",
    "pyimport_markers",
    "managed_imports",
    "comment_markers",
    "ref_markers",
    "unroll_markers",
)

_LIST_SECTIONS = frozenset(
    {
        "string_table",
        "path_table",
        "ast_path_table",
        "binding_sets",
        "locators",
        "records",
        "scopes",
        "markers",
        "pyimport_markers",
        "managed_imports",
        "comment_markers",
        "ref_markers",
        "unroll_markers",
    }
)
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_OBJECT_REPR = re.compile(r"<[^>\n]+ at 0x[0-9a-fA-F]+>")
_MEMORY_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{8,}\b")
_AST_PATH_SEGMENT = re.compile(r"^(?P<field>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<index>\d+)\])?$")


class PackageSnapshotFormatError(ValueError):
    """Raised when a lower-template package snapshot is not canonical data."""


class PackageSchemaMismatchError(PackageSnapshotFormatError):
    """Raised when package snapshot text uses an unsupported schema."""


@dataclass(frozen=True, slots=True)
class AstPathSegment:
    """One field/index segment in an AST path."""

    field: str
    index: int | None = None

    def snapshot(self) -> dict[str, object]:
        return {"field": self.field, "index": self.index}


@dataclass(frozen=True, slots=True)
class BindingSetRow:
    binding_set_id: int
    name_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LocatorRow:
    locator_id: int
    ast_path_id: int
    role_key_id: int
    parent_locator_id: int | None
    authored_summary_id: int
    materialization_anchor_id: int


@dataclass(frozen=True, slots=True)
class RecordRow:
    template_record_id: int
    surface_key_id: int
    operation_key_id: int | None
    locator_id: int
    resource_name_id: int | None
    inventory_kind_id: int
    owner_path_id: int
    semantic_summary_id: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScopeRow:
    scope_id: int
    parent_scope_id: int | None
    scope_kind_id: int
    ast_path_id: int
    owner_path_id: int
    local_binding_set_id: int
    argument_set_id: int


@dataclass(frozen=True, slots=True)
class MarkerRow:
    marker_id: int
    source_order: int
    marker_kind_id: int
    source_name_id: int
    operation_key_id: int
    scope_id: int
    owner_path_id: int
    ast_path_id: int
    statement_path_id: int | None
    resource_name_id: int | None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PyImportMarkerRow:
    pyimport_marker_id: int
    marker_id: int
    module_path_id: int | None
    name_ids: tuple[int, ...]
    as_name_id: int | None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ManagedImportRow:
    managed_import_id: int
    marker_id: int
    source_order: int
    scope_id: int
    module_path_id: int | None
    final_local_name_id: int
    original_symbol_id: int | None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommentMarkerRow:
    comment_marker_id: int
    marker_id: int
    payload_id: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RefMarkerRow:
    ref_marker_id: int
    marker_id: int
    ref_kind_id: int
    context_id: int
    sentinel_attr_id: int | None
    literal_path_id: int | None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnrollMarkerRow:
    unroll_marker_id: int
    marker_id: int
    statement_path_id: int
    target_ast_path_id: int
    iter_ast_path_id: int
    domain_ast_path_id: int
    body_path_id: int
    orelse_path_id: int | None
    target_binding_set_id: int
    domain_shape_id: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PackageBindingIndex:
    bindings_by_scope_id: dict[int, frozenset[str]]
    arguments_by_scope_id: dict[int, frozenset[str]]
    scope_ids_by_owner_path: dict[tuple[str, ...], tuple[int, ...]]


class LowerTemplatePackageV2:
    """Canonical lower-template package rows for one registered template."""

    def __init__(
        self,
        *,
        template_key: str,
        source_summary: str,
        surface_bundle_signature: str = "",
    ) -> None:
        self._strings: list[str] = []
        self._string_index: dict[str, int] = {}
        self._paths: list[tuple[str, ...]] = []
        self._path_index: dict[tuple[str, ...], int] = {}
        self._ast_paths: list[tuple[AstPathSegment, ...]] = []
        self._ast_path_texts: list[str] = []
        self._ast_path_index: dict[str, int] = {}
        self._binding_set_index: dict[tuple[str, ...], int] = {}

        self.surface_bundle_signature_id = self.intern_string(
            surface_bundle_signature
        )
        self.template_key_id = self.intern_string(template_key)
        self.source_summary_id = self.intern_string(source_summary)

        self.binding_sets: list[BindingSetRow] = []
        self.locators: list[LocatorRow] = []
        self.records: list[RecordRow] = []
        self.scopes: list[ScopeRow] = []
        self.markers: list[MarkerRow] = []
        self.pyimport_markers: list[PyImportMarkerRow] = []
        self.managed_imports: list[ManagedImportRow] = []
        self.comment_markers: list[CommentMarkerRow] = []
        self.ref_markers: list[RefMarkerRow] = []
        self.unroll_markers: list[UnrollMarkerRow] = []
        self._binding_index: PackageBindingIndex | None = None
        self._marker_ids_by_kind: dict[str, tuple[int, ...]] | None = None
        self._marker_ids_by_scope_id: dict[int, tuple[int, ...]] | None = None

    def intern_string(self, value: str) -> int:
        """Return a package-local string id, assigning it if needed."""
        existing = self._string_index.get(value)
        if existing is not None:
            return existing
        string_id = len(self._strings)
        self._strings.append(value)
        self._string_index[value] = string_id
        return string_id

    def intern_path(self, parts: tuple[str, ...]) -> int:
        """Return a package-local path id."""
        existing = self._path_index.get(parts)
        if existing is not None:
            return existing
        for part in parts:
            self.intern_string(part)
        path_id = len(self._paths)
        self._paths.append(parts)
        self._path_index[parts] = path_id
        return path_id

    def intern_ast_path(self, ast_path: str) -> int:
        """Return a package-local AST path id."""
        existing = self._ast_path_index.get(ast_path)
        if existing is not None:
            return existing
        ast_path_id = len(self._ast_paths)
        self._ast_paths.append(_parse_ast_path(ast_path))
        self._ast_path_texts.append(ast_path)
        self._ast_path_index[ast_path] = ast_path_id
        return ast_path_id

    def intern_binding_set(self, names: tuple[str, ...]) -> int:
        """Return a package-local binding-set id for a deterministic name set."""
        canonical = tuple(sorted(dict.fromkeys(names)))
        existing = self._binding_set_index.get(canonical)
        if existing is not None:
            return existing
        name_ids = tuple(self.intern_string(name) for name in canonical)
        binding_set_id = len(self.binding_sets)
        self.binding_sets.append(
            BindingSetRow(
                binding_set_id=binding_set_id,
                name_ids=name_ids,
            )
        )
        self._binding_set_index[canonical] = binding_set_id
        return binding_set_id

    def add_locator(
        self,
        *,
        ast_path: str,
        role_key: str,
        authored_summary: str,
        materialization_anchor: str,
        parent_locator_id: int | None = None,
        locator_id: int | None = None,
    ) -> int:
        """Append a locator row and return its id."""
        resolved_locator_id = (
            len(self.locators) if locator_id is None else locator_id
        )
        self.locators.append(
            LocatorRow(
                locator_id=resolved_locator_id,
                ast_path_id=self.intern_ast_path(ast_path),
                role_key_id=self.intern_string(role_key),
                parent_locator_id=parent_locator_id,
                authored_summary_id=self.intern_string(authored_summary),
                materialization_anchor_id=self.intern_string(
                    materialization_anchor
                ),
            )
        )
        return resolved_locator_id

    def add_record(
        self,
        *,
        surface_key: str,
        locator_id: int,
        inventory_kind: str,
        owner_path: tuple[str, ...],
        semantic_summary: str,
        operation_key: str | None = None,
        resource_name: str = "",
        flags: tuple[str, ...] = (),
        template_record_id: int | None = None,
    ) -> int:
        """Append a template record row and return its id."""
        resolved_template_record_id = (
            len(self.records)
            if template_record_id is None
            else template_record_id
        )
        self.records.append(
            RecordRow(
                template_record_id=resolved_template_record_id,
                surface_key_id=self.intern_string(surface_key),
                operation_key_id=(
                    None
                    if operation_key is None
                    else self.intern_string(operation_key)
                ),
                locator_id=locator_id,
                resource_name_id=(
                    None if resource_name == "" else self.intern_string(resource_name)
                ),
                inventory_kind_id=self.intern_string(inventory_kind),
                owner_path_id=self.intern_path(owner_path),
                semantic_summary_id=self.intern_string(semantic_summary),
                flags=tuple(flags),
            )
        )
        return resolved_template_record_id

    def add_scope(
        self,
        *,
        scope_kind: str,
        ast_path: str,
        owner_path: tuple[str, ...],
        local_bindings: tuple[str, ...] = (),
        arguments: tuple[str, ...] = (),
        parent_scope_id: int | None = None,
    ) -> int:
        """Append a scope row and return its id."""
        scope_id = len(self.scopes)
        self.scopes.append(
            ScopeRow(
                scope_id=scope_id,
                parent_scope_id=parent_scope_id,
                scope_kind_id=self.intern_string(scope_kind),
                ast_path_id=self.intern_ast_path(ast_path),
                owner_path_id=self.intern_path(owner_path),
                local_binding_set_id=self.intern_binding_set(local_bindings),
                argument_set_id=self.intern_binding_set(arguments),
            )
        )
        self._binding_index = None
        return scope_id

    def add_marker(
        self,
        *,
        marker_kind: str,
        source_name: str,
        ast_path: str,
        statement_path: str | None,
        owner_path: tuple[str, ...],
        scope_id: int,
        source_order: int,
        resource_name: str = "",
        operation_key: str = "",
        flags: tuple[str, ...] = (),
    ) -> int:
        """Append a marker row and return its id."""
        marker_id = len(self.markers)
        self.markers.append(
            MarkerRow(
                marker_id=marker_id,
                source_order=source_order,
                marker_kind_id=self.intern_string(marker_kind),
                source_name_id=self.intern_string(source_name),
                operation_key_id=self.intern_string(operation_key),
                scope_id=scope_id,
                owner_path_id=self.intern_path(owner_path),
                ast_path_id=self.intern_ast_path(ast_path),
                statement_path_id=(
                    None
                    if statement_path is None
                    else self.intern_ast_path(statement_path)
                ),
                resource_name_id=(
                    None if resource_name == "" else self.intern_string(resource_name)
                ),
                flags=tuple(flags),
            )
        )
        self._marker_ids_by_kind = None
        self._marker_ids_by_scope_id = None
        return marker_id

    def add_pyimport_marker(
        self,
        *,
        marker_id: int,
        module_path: tuple[str, ...] | None,
        names: tuple[str, ...] = (),
        as_name: str = "",
        flags: tuple[str, ...] = (),
    ) -> int:
        """Append typed source facts for an ``astichi_pyimport`` marker."""
        pyimport_marker_id = len(self.pyimport_markers)
        self.pyimport_markers.append(
            PyImportMarkerRow(
                pyimport_marker_id=pyimport_marker_id,
                marker_id=marker_id,
                module_path_id=(
                    None if module_path is None else self.intern_path(module_path)
                ),
                name_ids=tuple(self.intern_string(name) for name in names),
                as_name_id=None if as_name == "" else self.intern_string(as_name),
                flags=tuple(flags),
            )
        )
        self._add_managed_imports_for_pyimport(
            marker_id=marker_id,
            module_path=module_path,
            names=names,
            as_name=as_name,
            flags=flags,
        )
        return pyimport_marker_id

    def _add_managed_imports_for_pyimport(
        self,
        *,
        marker_id: int,
        module_path: tuple[str, ...] | None,
        names: tuple[str, ...],
        as_name: str,
        flags: tuple[str, ...],
    ) -> None:
        marker = self.markers[marker_id]
        if names:
            for name in names:
                self._add_managed_import(
                    marker=marker,
                    module_path=module_path,
                    final_local_name=name,
                    original_symbol=name,
                    flags=flags,
                )
            return
        if as_name != "":
            self._add_managed_import(
                marker=marker,
                module_path=module_path,
                final_local_name=as_name,
                original_symbol=None,
                flags=flags,
            )
            return
        if module_path is not None and len(module_path) == 1:
            self._add_managed_import(
                marker=marker,
                module_path=module_path,
                final_local_name=module_path[0],
                original_symbol=None,
                flags=flags,
            )

    def _add_managed_import(
        self,
        *,
        marker: MarkerRow,
        module_path: tuple[str, ...] | None,
        final_local_name: str,
        original_symbol: str | None,
        flags: tuple[str, ...],
    ) -> int:
        managed_import_id = len(self.managed_imports)
        self.managed_imports.append(
            ManagedImportRow(
                managed_import_id=managed_import_id,
                marker_id=marker.marker_id,
                source_order=marker.source_order,
                scope_id=marker.scope_id,
                module_path_id=(
                    None if module_path is None else self.intern_path(module_path)
                ),
                final_local_name_id=self.intern_string(final_local_name),
                original_symbol_id=(
                    None
                    if original_symbol is None
                    else self.intern_string(original_symbol)
                ),
                flags=tuple(flags),
            )
        )
        return managed_import_id

    def add_comment_marker(
        self,
        *,
        marker_id: int,
        payload: str,
        flags: tuple[str, ...] = (),
    ) -> int:
        """Append typed source facts for an ``astichi_comment`` marker."""
        comment_marker_id = len(self.comment_markers)
        self.comment_markers.append(
            CommentMarkerRow(
                comment_marker_id=comment_marker_id,
                marker_id=marker_id,
                payload_id=self.intern_string(payload),
                flags=tuple(flags),
            )
        )
        return comment_marker_id

    def add_ref_marker(
        self,
        *,
        marker_id: int,
        ref_kind: str,
        context: str,
        sentinel_attr: str = "",
        literal_path: tuple[str, ...] | None = None,
        flags: tuple[str, ...] = (),
    ) -> int:
        """Append typed source facts for an ``astichi_ref`` marker."""
        ref_marker_id = len(self.ref_markers)
        self.ref_markers.append(
            RefMarkerRow(
                ref_marker_id=ref_marker_id,
                marker_id=marker_id,
                ref_kind_id=self.intern_string(ref_kind),
                context_id=self.intern_string(context),
                sentinel_attr_id=(
                    None if sentinel_attr == "" else self.intern_string(sentinel_attr)
                ),
                literal_path_id=(
                    None if literal_path is None else self.intern_path(literal_path)
                ),
                flags=tuple(flags),
            )
        )
        return ref_marker_id

    def add_unroll_marker(
        self,
        *,
        marker_id: int,
        statement_path: str,
        target_ast_path: str,
        iter_ast_path: str,
        domain_ast_path: str,
        body_path: str,
        orelse_path: str | None,
        target_bindings: tuple[str, ...] = (),
        domain_shape: str = "",
        flags: tuple[str, ...] = (),
    ) -> int:
        """Append typed source facts for an ``astichi_for`` marker."""
        unroll_marker_id = len(self.unroll_markers)
        self.unroll_markers.append(
            UnrollMarkerRow(
                unroll_marker_id=unroll_marker_id,
                marker_id=marker_id,
                statement_path_id=self.intern_ast_path(statement_path),
                target_ast_path_id=self.intern_ast_path(target_ast_path),
                iter_ast_path_id=self.intern_ast_path(iter_ast_path),
                domain_ast_path_id=self.intern_ast_path(domain_ast_path),
                body_path_id=self.intern_ast_path(body_path),
                orelse_path_id=(
                    None if orelse_path is None else self.intern_ast_path(orelse_path)
                ),
                target_binding_set_id=self.intern_binding_set(target_bindings),
                domain_shape_id=self.intern_string(domain_shape),
                flags=tuple(flags),
            )
        )
        return unroll_marker_id

    def records_by_owner_path(self, owner_path: tuple[str, ...]) -> tuple[RecordRow, ...]:
        """Return record rows owned by one package-local owner path."""
        path_id = self._path_index.get(owner_path)
        if path_id is None:
            return ()
        return tuple(record for record in self.records if record.owner_path_id == path_id)

    def binding_names_for_scope_id(self, scope_id: int) -> frozenset[str]:
        """Return local binding names for one scope row."""
        return self._bindings_index().bindings_by_scope_id.get(scope_id, frozenset())

    def argument_names_for_scope_id(self, scope_id: int) -> frozenset[str]:
        """Return argument binding names for one function scope row."""
        return self._bindings_index().arguments_by_scope_id.get(scope_id, frozenset())

    def scope_ids_for_owner_path(self, owner_path: tuple[str, ...]) -> tuple[int, ...]:
        """Return scope ids with one owner path."""
        return self._bindings_index().scope_ids_by_owner_path.get(owner_path, ())

    def boundary_available_names_for_statement_path(
        self,
        statement_path: str,
    ) -> frozenset[str]:
        """Return the binding view used by lower boundary collision checks."""
        scope_id = self._scope_id_for_statement_path(statement_path)
        if scope_id is None:
            return frozenset()
        return self.binding_names_for_scope_id(scope_id)

    def scope_id_for_statement_path(self, statement_path: str) -> int | None:
        """Return the innermost lexical scope id for one statement path."""
        return self._scope_id_for_statement_path(statement_path)

    def pyimport_existing_binding_names(self) -> frozenset[str]:
        """Return the module binding view used for pyimport collision checks."""
        if not self.scopes:
            return frozenset()
        return self.binding_names_for_scope_id(self.scopes[0].scope_id)

    def marker_ids_by_kind(self, marker_kind: str) -> tuple[int, ...]:
        """Return marker ids with one marker kind."""
        return self._markers_by_kind().get(marker_kind, ())

    def marker_ids_by_scope_id(self, scope_id: int) -> tuple[int, ...]:
        """Return marker ids owned by one scope id."""
        return self._markers_by_scope_id().get(scope_id, ())

    def boundary_markers_supported(
        self,
        available_names: frozenset[str],
        *,
        scope_id: int | None = None,
    ) -> bool:
        """Return whether boundary markers can connect to available names."""
        marker_rows = self.markers
        if scope_id is not None:
            marker_ids = set(self.marker_ids_by_scope_id(scope_id))
            marker_rows = [row for row in marker_rows if row.marker_id in marker_ids]
        for row in marker_rows:
            source_name = self._string(row.source_name_id)
            if source_name in {"astichi_elif", "astichi_export"}:
                continue
            if source_name not in {"astichi_import", "astichi_pass"}:
                return False
            name = self._optional_string(row.resource_name_id)
            if name == "":
                return False
            flags = frozenset(row.flags)
            if (
                "explicit_bind_enabled" in flags
                or "outer_bind_enabled" in flags
                or name in available_names
            ):
                continue
            return False
        return True

    def marker_source_name(self, row: MarkerRow) -> str:
        """Return the source marker spelling for a marker row."""
        return self._string(row.source_name_id)

    def marker_resource_name(self, row: MarkerRow) -> str:
        """Return the name-bearing resource for a marker row, if any."""
        return self._optional_string(row.resource_name_id)

    def managed_import_module_path(
        self,
        row: ManagedImportRow,
    ) -> tuple[str, ...] | None:
        """Return the resolved module path for a managed import row, if known."""
        return None if row.module_path_id is None else self._path(row.module_path_id)

    def managed_import_final_local_name(self, row: ManagedImportRow) -> str:
        """Return the final local binding name for a managed import row."""
        return self._string(row.final_local_name_id)

    def managed_import_original_symbol(self, row: ManagedImportRow) -> str | None:
        """Return the original imported symbol for a managed from-import row."""
        if row.original_symbol_id is None:
            return None
        return self._string(row.original_symbol_id)

    def record_inventory_kind(self, row: RecordRow) -> str:
        """Return the inventory kind for a template record row."""
        return self._string(row.inventory_kind_id)

    def structural_template_snapshot(self, *, template_id: int = 0) -> dict[str, object]:
        """Render the v1 structural template row from package data."""
        return {
            "record_count": len(self.records),
            "source_summary": self._string(self.source_summary_id),
            "template_id": template_id,
            "template_key": self._string(self.template_key_id),
        }

    def structural_locator_snapshots(self, *, template_id: int = 0) -> list[dict[str, object]]:
        """Render v1 structural locator rows from package locator rows."""
        return [
            {
                "ast_path": self._ast_path_text(locator.ast_path_id),
                "authored_summary": self._string(locator.authored_summary_id),
                "locator_id": locator.locator_id,
                "materialization_anchor": self._string(
                    locator.materialization_anchor_id
                ),
                "parent_locator_id": locator.parent_locator_id,
                "role_key": self._string(locator.role_key_id),
                "template_id": template_id,
            }
            for locator in self.locators
        ]

    def structural_record_snapshot(
        self,
        *,
        template_record_id: int,
        occurrence_id: int,
        visible: bool,
        satisfied: bool,
    ) -> dict[str, object]:
        """Render the v1 structural record metadata from one package row."""
        record = self.records[template_record_id]
        return {
            "code_owner": list(self._path(record.owner_path_id)),
            "inventory_kind": self._string(record.inventory_kind_id),
            "locator_id": record.locator_id,
            "occurrence_id": occurrence_id,
            "record_id": [occurrence_id, record.template_record_id],
            "resource_name": self._optional_string(record.resource_name_id),
            "semantic_summary": self._string(record.semantic_summary_id),
            "state": {
                "satisfied": satisfied,
                "visible": visible,
            },
            "surface_key": self._string(record.surface_key_id),
            "template_record_id": record.template_record_id,
        }

    def snapshot(self) -> dict[str, object]:
        """Return the deterministic package snapshot projection."""
        return {
            "schema": SCHEMA,
            "surface_bundle_signature": self._string(
                self.surface_bundle_signature_id
            ),
            "template_key": self._string(self.template_key_id),
            "source_summary": self._string(self.source_summary_id),
            "string_table": list(self._strings),
            "path_table": [list(path) for path in self._paths],
            "ast_path_table": [self._ast_path_text(index) for index in range(len(self._ast_paths))],
            "binding_sets": [self._binding_set_snapshot(row) for row in self.binding_sets],
            "locators": [self._locator_snapshot(row) for row in self.locators],
            "records": [self._record_snapshot(row) for row in self.records],
            "scopes": [self._scope_snapshot(row) for row in self.scopes],
            "markers": [self._marker_snapshot(row) for row in self.markers],
            "pyimport_markers": [
                self._pyimport_marker_snapshot(row)
                for row in self.pyimport_markers
            ],
            "managed_imports": [
                self._managed_import_snapshot(row)
                for row in self.managed_imports
            ],
            "comment_markers": [
                self._comment_marker_snapshot(row)
                for row in self.comment_markers
            ],
            "ref_markers": [
                self._ref_marker_snapshot(row)
                for row in self.ref_markers
            ],
            "unroll_markers": [
                self._unroll_marker_snapshot(row)
                for row in self.unroll_markers
            ],
        }

    def ast_path_segments(self, ast_path_id: int) -> tuple[AstPathSegment, ...]:
        """Return parsed AST path segments for hot-path users."""
        return self._ast_paths[ast_path_id]

    def _bindings_index(self) -> PackageBindingIndex:
        if self._binding_index is None:
            scope_ids_by_owner: dict[tuple[str, ...], list[int]] = {}
            bindings_by_scope_id: dict[int, frozenset[str]] = {}
            arguments_by_scope_id: dict[int, frozenset[str]] = {}
            for row in self.scopes:
                owner_path = self._path(row.owner_path_id)
                scope_ids_by_owner.setdefault(owner_path, []).append(row.scope_id)
                bindings_by_scope_id[row.scope_id] = frozenset(
                    self._binding_set_names(row.local_binding_set_id)
                )
                arguments_by_scope_id[row.scope_id] = frozenset(
                    self._binding_set_names(row.argument_set_id)
                )
            self._binding_index = PackageBindingIndex(
                bindings_by_scope_id=bindings_by_scope_id,
                arguments_by_scope_id=arguments_by_scope_id,
                scope_ids_by_owner_path={
                    owner_path: tuple(scope_ids)
                    for owner_path, scope_ids in scope_ids_by_owner.items()
                },
            )
        return self._binding_index

    def _scope_id_for_statement_path(self, statement_path: str) -> int | None:
        best_scope_id: int | None = None
        best_depth = -1
        for row in self.scopes:
            scope_path = self._ast_path_text(row.ast_path_id)
            if not _ast_path_is_prefix(scope_path, statement_path):
                continue
            depth = _ast_path_depth(scope_path)
            if depth > best_depth:
                best_scope_id = row.scope_id
                best_depth = depth
        return best_scope_id

    def _markers_by_kind(self) -> dict[str, tuple[int, ...]]:
        if self._marker_ids_by_kind is None:
            marker_ids_by_kind: dict[str, list[int]] = {}
            for row in self.markers:
                marker_kind = self._string(row.marker_kind_id)
                marker_ids_by_kind.setdefault(marker_kind, []).append(row.marker_id)
            self._marker_ids_by_kind = {
                marker_kind: tuple(marker_ids)
                for marker_kind, marker_ids in marker_ids_by_kind.items()
            }
        return self._marker_ids_by_kind

    def _markers_by_scope_id(self) -> dict[int, tuple[int, ...]]:
        if self._marker_ids_by_scope_id is None:
            marker_ids_by_scope_id: dict[int, list[int]] = {}
            for row in self.markers:
                marker_ids_by_scope_id.setdefault(row.scope_id, []).append(
                    row.marker_id
                )
            self._marker_ids_by_scope_id = {
                scope_id: tuple(marker_ids)
                for scope_id, marker_ids in marker_ids_by_scope_id.items()
            }
        return self._marker_ids_by_scope_id

    def _binding_set_snapshot(self, row: BindingSetRow) -> dict[str, object]:
        return {
            "binding_set_id": row.binding_set_id,
            "names": [self._string(name_id) for name_id in row.name_ids],
        }

    def _locator_snapshot(self, row: LocatorRow) -> dict[str, object]:
        return {
            "ast_path": self._ast_path_text(row.ast_path_id),
            "authored_summary": self._string(row.authored_summary_id),
            "locator_id": row.locator_id,
            "materialization_anchor": self._string(row.materialization_anchor_id),
            "parent_locator_id": row.parent_locator_id,
            "role_key": self._string(row.role_key_id),
        }

    def _record_snapshot(self, row: RecordRow) -> dict[str, object]:
        return {
            "flags": list(row.flags),
            "inventory_kind": self._string(row.inventory_kind_id),
            "locator_id": row.locator_id,
            "operation_key": self._optional_string(row.operation_key_id),
            "owner_path": list(self._path(row.owner_path_id)),
            "resource_name": self._optional_string(row.resource_name_id),
            "semantic_summary": self._string(row.semantic_summary_id),
            "surface_key": self._string(row.surface_key_id),
            "template_record_id": row.template_record_id,
        }

    def _scope_snapshot(self, row: ScopeRow) -> dict[str, object]:
        return {
            "arguments": self._binding_set_names(row.argument_set_id),
            "ast_path": self._ast_path_text(row.ast_path_id),
            "local_bindings": self._binding_set_names(row.local_binding_set_id),
            "owner_path": list(self._path(row.owner_path_id)),
            "parent_scope_id": row.parent_scope_id,
            "scope_id": row.scope_id,
            "scope_kind": self._string(row.scope_kind_id),
        }

    def _marker_snapshot(self, row: MarkerRow) -> dict[str, object]:
        return {
            "ast_path": self._ast_path_text(row.ast_path_id),
            "flags": list(row.flags),
            "marker_id": row.marker_id,
            "marker_kind": self._string(row.marker_kind_id),
            "operation_key": self._string(row.operation_key_id),
            "owner_path": list(self._path(row.owner_path_id)),
            "resource_name": self._optional_string(row.resource_name_id),
            "scope_id": row.scope_id,
            "source_name": self._string(row.source_name_id),
            "source_order": row.source_order,
            "statement_path": (
                None
                if row.statement_path_id is None
                else self._ast_path_text(row.statement_path_id)
            ),
        }

    def _pyimport_marker_snapshot(
        self,
        row: PyImportMarkerRow,
    ) -> dict[str, object]:
        return {
            "as_name": self._optional_string(row.as_name_id),
            "flags": list(row.flags),
            "marker_id": row.marker_id,
            "module_path": (
                None
                if row.module_path_id is None
                else list(self._path(row.module_path_id))
            ),
            "names": [self._string(name_id) for name_id in row.name_ids],
            "pyimport_marker_id": row.pyimport_marker_id,
        }

    def _comment_marker_snapshot(
        self,
        row: CommentMarkerRow,
    ) -> dict[str, object]:
        return {
            "comment_marker_id": row.comment_marker_id,
            "flags": list(row.flags),
            "marker_id": row.marker_id,
            "payload": self._string(row.payload_id),
        }

    def _managed_import_snapshot(
        self,
        row: ManagedImportRow,
    ) -> dict[str, object]:
        return {
            "final_local_name": self._string(row.final_local_name_id),
            "flags": list(row.flags),
            "managed_import_id": row.managed_import_id,
            "marker_id": row.marker_id,
            "module_path": (
                None
                if row.module_path_id is None
                else list(self._path(row.module_path_id))
            ),
            "original_symbol": (
                None
                if row.original_symbol_id is None
                else self._string(row.original_symbol_id)
            ),
            "scope_id": row.scope_id,
            "source_order": row.source_order,
        }

    def _ref_marker_snapshot(
        self,
        row: RefMarkerRow,
    ) -> dict[str, object]:
        return {
            "context": self._string(row.context_id),
            "flags": list(row.flags),
            "literal_path": (
                None
                if row.literal_path_id is None
                else list(self._path(row.literal_path_id))
            ),
            "marker_id": row.marker_id,
            "ref_kind": self._string(row.ref_kind_id),
            "ref_marker_id": row.ref_marker_id,
            "sentinel_attr": self._optional_string(row.sentinel_attr_id),
        }

    def _unroll_marker_snapshot(
        self,
        row: UnrollMarkerRow,
    ) -> dict[str, object]:
        return {
            "body_path": self._ast_path_text(row.body_path_id),
            "domain_ast_path": self._ast_path_text(row.domain_ast_path_id),
            "domain_shape": self._string(row.domain_shape_id),
            "flags": list(row.flags),
            "iter_ast_path": self._ast_path_text(row.iter_ast_path_id),
            "marker_id": row.marker_id,
            "orelse_path": (
                None
                if row.orelse_path_id is None
                else self._ast_path_text(row.orelse_path_id)
            ),
            "statement_path": self._ast_path_text(row.statement_path_id),
            "target_ast_path": self._ast_path_text(row.target_ast_path_id),
            "target_bindings": self._binding_set_names(row.target_binding_set_id),
            "unroll_marker_id": row.unroll_marker_id,
        }

    def _binding_set_names(self, binding_set_id: int) -> list[str]:
        row = self.binding_sets[binding_set_id]
        return [self._string(name_id) for name_id in row.name_ids]

    def _string(self, string_id: int) -> str:
        return self._strings[string_id]

    def _optional_string(self, string_id: int | None) -> str:
        return "" if string_id is None else self._string(string_id)

    def _path(self, path_id: int) -> tuple[str, ...]:
        return self._paths[path_id]

    def _ast_path_text(self, ast_path_id: int) -> str:
        return self._ast_path_texts[ast_path_id]


def write_package_snapshot(snapshot: Mapping[str, Any]) -> str:
    """Write lower-template package snapshot data as deterministic JSON text."""
    canonical = normalize_package_snapshot(snapshot)
    return json.dumps(canonical, indent=2, ensure_ascii=True) + "\n"


def read_package_snapshot(text: str) -> dict[str, Any]:
    """Read and validate lower-template package snapshot JSON."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PackageSnapshotFormatError(str(exc)) from exc
    return normalize_package_snapshot(raw)


def round_trip_package_snapshot_text(text: str) -> str:
    """Read and rewrite lower-template package snapshot text."""
    return write_package_snapshot(read_package_snapshot(text))


def normalize_package_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical package snapshot mapping."""
    if not isinstance(snapshot, Mapping):
        raise PackageSnapshotFormatError("package snapshot must be a JSON object")

    keys = set(snapshot)
    expected = set(SECTION_KEYS)
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing:
        raise PackageSnapshotFormatError(
            f"missing package snapshot sections: {missing}"
        )
    if extra:
        raise PackageSnapshotFormatError(
            f"unknown package snapshot sections: {extra}"
        )

    if snapshot["schema"] != SCHEMA:
        raise PackageSchemaMismatchError(
            f"unsupported package snapshot schema: {snapshot['schema']!r}"
        )

    for section in _LIST_SECTIONS:
        if not isinstance(snapshot[section], list):
            raise PackageSnapshotFormatError(f"{section} section must be a list")

    return {
        section: _canonical_json_value(snapshot[section], path=(section,))
        for section in SECTION_KEYS
    }


def _canonical_json_value(value: Any, *, path: tuple[str, ...]) -> Any:
    if value is None or isinstance(value, bool | int | str):
        if isinstance(value, str):
            _validate_stable_string(value, path=path)
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PackageSnapshotFormatError(
                f"non-finite float at {_format_path(path)}"
            )
        return value
    if isinstance(value, list | tuple):
        return [
            _canonical_json_value(item, path=(*path, f"[{index}]"))
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise PackageSnapshotFormatError(
                    f"object key at {_format_path(path)} is not a string"
                )
            normalized[key] = _canonical_json_value(value[key], path=(*path, key))
        return normalized
    raise PackageSnapshotFormatError(
        f"unsupported JSON value at {_format_path(path)}: {type(value).__name__}"
    )


def _parse_ast_path(ast_path: str) -> tuple[AstPathSegment, ...]:
    if ast_path == "":
        return ()
    separator = "/" if "/" in ast_path else "."
    segments: list[AstPathSegment] = []
    for raw_part in ast_path.split(separator):
        if raw_part == "":
            continue
        match = _AST_PATH_SEGMENT.match(raw_part)
        if match is None:
            segments.append(AstPathSegment(raw_part))
            continue
        index = match.group("index")
        segments.append(
            AstPathSegment(
                field=match.group("field"),
                index=None if index is None else int(index),
            )
        )
    return tuple(segments)


def _ast_path_is_prefix(scope_path: str, statement_path: str) -> bool:
    if scope_path == "":
        return True
    return statement_path == scope_path or statement_path.startswith(
        f"{scope_path}/"
    )


def _ast_path_depth(ast_path: str) -> int:
    if ast_path == "":
        return 0
    return len(tuple(part for part in ast_path.split("/") if part))


def _validate_stable_string(value: str, *, path: tuple[str, ...]) -> None:
    if value.startswith("/") or _WINDOWS_ABSOLUTE_PATH.match(value):
        raise PackageSnapshotFormatError(
            f"absolute path is not allowed at {_format_path(path)}"
        )
    if _OBJECT_REPR.search(value) or _MEMORY_ADDRESS.search(value):
        raise PackageSnapshotFormatError(
            f"unstable object repr or memory address at {_format_path(path)}"
        )


def _format_path(path: tuple[str, ...]) -> str:
    return ".".join(path)
