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
        return scope_id

    def records_by_owner_path(self, owner_path: tuple[str, ...]) -> tuple[RecordRow, ...]:
        """Return record rows owned by one package-local owner path."""
        path_id = self._path_index.get(owner_path)
        if path_id is None:
            return ()
        return tuple(record for record in self.records if record.owner_path_id == path_id)

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
        }

    def ast_path_segments(self, ast_path_id: int) -> tuple[AstPathSegment, ...]:
        """Return parsed AST path segments for hot-path users."""
        return self._ast_paths[ast_path_id]

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
