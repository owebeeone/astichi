"""Canonical structural snapshots for lower-engine validation."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

SCHEMA = "astichi.structural-inventory.v1"

SECTION_KEYS: tuple[str, ...] = (
    "schema",
    "surface_bundle",
    "templates",
    "locators",
    "occurrences",
    "records",
    "edges",
    "overlays",
    "materialization",
    "diagnostics",
)

_LIST_SECTIONS = frozenset(
    {
        "templates",
        "locators",
        "occurrences",
        "records",
        "edges",
        "overlays",
        "diagnostics",
    }
)
_MAP_SECTIONS = frozenset({"surface_bundle", "materialization"})
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_OBJECT_REPR = re.compile(r"<[^>\n]+ at 0x[0-9a-fA-F]+>")
_MEMORY_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{8,}\b")


class SnapshotFormatError(ValueError):
    """Raised when structural snapshot text is not canonical v1 data."""


class SchemaMismatchError(SnapshotFormatError):
    """Raised when structural snapshot text uses an unsupported schema."""


def read_structural_snapshot(text: str) -> dict[str, Any]:
    """Read and validate structural snapshot JSON."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotFormatError(str(exc)) from exc
    return normalize_structural_snapshot(raw)


def write_structural_snapshot(snapshot: Mapping[str, Any]) -> str:
    """Write structural snapshot data as deterministic JSON text."""
    canonical = normalize_structural_snapshot(snapshot)
    return json.dumps(canonical, indent=2, ensure_ascii=True) + "\n"


def round_trip_structural_snapshot_text(text: str) -> str:
    """Read and rewrite structural snapshot text."""
    return write_structural_snapshot(read_structural_snapshot(text))


def normalize_structural_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical structural snapshot mapping."""
    if not isinstance(snapshot, Mapping):
        raise SnapshotFormatError("structural snapshot must be a JSON object")

    keys = set(snapshot)
    expected = set(SECTION_KEYS)
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing:
        raise SnapshotFormatError(f"missing structural snapshot sections: {missing}")
    if extra:
        raise SnapshotFormatError(f"unknown structural snapshot sections: {extra}")

    if snapshot["schema"] != SCHEMA:
        raise SchemaMismatchError(
            f"unsupported structural snapshot schema: {snapshot['schema']!r}"
        )

    for section in _LIST_SECTIONS:
        if not isinstance(snapshot[section], list):
            raise SnapshotFormatError(f"{section} section must be a list")
    for section in _MAP_SECTIONS:
        if not isinstance(snapshot[section], Mapping):
            raise SnapshotFormatError(f"{section} section must be an object")

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
            raise SnapshotFormatError(f"non-finite float at {_format_path(path)}")
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
                raise SnapshotFormatError(
                    f"object key at {_format_path(path)} is not a string"
                )
            normalized[key] = _canonical_json_value(value[key], path=(*path, key))
        return normalized
    raise SnapshotFormatError(
        f"unsupported JSON value at {_format_path(path)}: {type(value).__name__}"
    )


def _validate_stable_string(value: str, *, path: tuple[str, ...]) -> None:
    if value.startswith("/") or _WINDOWS_ABSOLUTE_PATH.match(value):
        raise SnapshotFormatError(
            f"absolute path is not allowed at {_format_path(path)}"
        )
    if _OBJECT_REPR.search(value) or _MEMORY_ADDRESS.search(value):
        raise SnapshotFormatError(
            f"unstable object repr or memory address at {_format_path(path)}"
        )


def _format_path(path: tuple[str, ...]) -> str:
    return ".".join(path)
