from __future__ import annotations

import json

import pytest

from astichi.structural_snapshot import (
    SCHEMA,
    SchemaMismatchError,
    SnapshotFormatError,
    read_structural_snapshot,
    round_trip_structural_snapshot_text,
    write_structural_snapshot,
)


def test_structural_snapshot_writer_is_deterministic() -> None:
    snapshot = _minimal_snapshot()

    text = write_structural_snapshot(snapshot)

    assert round_trip_structural_snapshot_text(text) == text
    assert text.startswith('{\n  "schema": "astichi.structural-inventory.v1",\n')


def test_structural_snapshot_rejects_unknown_schema() -> None:
    snapshot = _minimal_snapshot()
    snapshot["schema"] = "astichi.structural-inventory.v2"

    with pytest.raises(SchemaMismatchError, match="unsupported structural snapshot schema"):
        write_structural_snapshot(snapshot)


def test_structural_snapshot_rejects_unknown_sections() -> None:
    snapshot = _minimal_snapshot()
    snapshot["debug"] = {}

    with pytest.raises(SnapshotFormatError, match="unknown structural snapshot sections"):
        write_structural_snapshot(snapshot)


def test_structural_snapshot_rejects_unstable_strings() -> None:
    snapshot = _minimal_snapshot()
    snapshot["locators"].append(
        {
            "ast_path": "/" + "tmp/local/file.py",
            "authored_summary": "bad",
            "locator_id": 0,
            "materialization_anchor": "debug",
            "parent_locator_id": None,
            "role_key": "source",
            "template_id": 0,
        }
    )

    with pytest.raises(SnapshotFormatError, match="absolute path"):
        write_structural_snapshot(snapshot)


def test_structural_snapshot_reader_rejects_non_json_object() -> None:
    with pytest.raises(SnapshotFormatError, match="must be a JSON object"):
        read_structural_snapshot(json.dumps([]))


def _minimal_snapshot() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "surface_bundle": {
            "bundle_key": "astichi.test.minimal",
            "operations": [],
            "patterns": [],
            "schema_version": 1,
            "surfaces": [],
        },
        "templates": [],
        "locators": [],
        "occurrences": [],
        "records": [],
        "edges": [],
        "overlays": [],
        "materialization": {
            "artifact_requests": [],
            "debug_views": {},
            "hygiene_stream": [],
            "operation_stream": [],
            "root_occurrence_id": None,
        },
        "diagnostics": [],
    }
