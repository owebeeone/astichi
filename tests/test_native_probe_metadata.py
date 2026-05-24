from __future__ import annotations

from native_probe.native_probe import (
    constructor_compatibility_table,
    minimal_template_scan,
)


def test_native_probe_minimal_template_scan_counts_marker_mentions() -> None:
    source = "class Box__astichi_arg__:\n    value = astichi_hole(slot)\n"

    assert minimal_template_scan(source) == {
        "class_mentions": 1,
        "def_mentions": 0,
        "line_count": 2,
        "marker_mentions": 4,
        "source_bytes": len(source.encode()),
    }


def test_native_probe_constructor_table_covers_probe_surface() -> None:
    table = constructor_compatibility_table()
    rows = {row["class"]: row for row in table}

    assert {"Module", "FunctionDef", "ClassDef", "Try", "With"} <= set(rows)
    assert rows["Module"]["full_constructor"]["status"] == "ok"
    assert rows["FunctionDef"]["location_required_for_compile"] is True
