from __future__ import annotations

import pytest

import astichi
from astichi.assembler import AssemblyScope
from astichi.lower_engine import LowerEngine, current_surface_bundle_spec
from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.structural_snapshot import write_structural_snapshot


def test_native_occurrence_store_capability_when_available() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    assert "native.occurrence_store.v1" in capabilities["engine_features"]
    assert "native.record_indexes.v1" in capabilities["engine_features"]


def test_native_occurrence_store_root_snapshot_matches_python_scope_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    source = "result = astichi_hole(value)\n"
    handle = _engine_with_current_bundle(module)
    template = _register_template_source(module, handle, source)
    state = module.assembly_state_create(handle)

    module.assembly_state_append_occurrence(handle, state, template, ("Root",))

    actual = module.assembly_state_snapshot(handle, state)
    scope = AssemblyScope(astichi.build())
    scope.add("Root", astichi.compile(source))
    expected = scope.lower_structural_snapshot()

    assert actual == expected
    assert write_structural_snapshot(actual) == write_structural_snapshot(expected)


def test_native_occurrence_store_appends_child_occurrence_and_indexes_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    handle = _engine_with_current_bundle(module)
    root_template = _register_template_source(
        module,
        handle,
        "result = astichi_hole(value)\n",
    )
    value_template = _register_template_source(module, handle, "1\n")
    state = module.assembly_state_create(handle)

    root_occurrence = module.assembly_state_append_occurrence(
        handle,
        state,
        root_template,
        ("Root",),
    )
    child_occurrence = module.assembly_state_append_occurrence(
        handle,
        state,
        value_template,
        ("Root", "Value"),
        root_occurrence,
    )
    record = module.assembly_state_record_handle(handle, state, root_occurrence, 0)

    snapshot = module.assembly_state_snapshot(handle, state)
    indexes = module.assembly_state_index_snapshot(handle, state)

    record_snapshot = record.snapshot()

    assert root_occurrence.snapshot()["kind"] == "occurrence"
    assert child_occurrence.snapshot()["state_index"] == root_occurrence.state_index
    assert record_snapshot["kind"] == "record"
    assert record_snapshot["occurrence_index"] == 0
    assert record_snapshot["state_index"] == 0
    assert record_snapshot["template_record_index"] == 0
    assert snapshot["occurrences"][1] == {
        "build_path": ["Root", "Value"],
        "occurrence_id": 1,
        "parent_occurrence_id": 0,
        "template_id": 1,
    }
    assert _index_entry(indexes["by_build_path"], ["Root"])["records"] == [
        [0, 0],
        [0, 1],
    ]
    assert _index_entry(indexes["by_resource_name"], "value")["records"] == [[0, 0]]
    assert _index_entry(indexes["by_inventory_kind"], "hole.expr")["records"] == [[0, 0]]
    assert _index_entry(indexes["by_name_and_kind"], ["value", "hole.expr"])[
        "records"
    ] == [[0, 0]]


def test_native_occurrence_store_rejects_cross_engine_handles_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    first = _engine_with_current_bundle(module)
    second = _engine_with_current_bundle(module)
    template = _register_template_source(module, first, "result = astichi_hole(value)\n")
    state = module.assembly_state_create(first)

    with pytest.raises(RuntimeError, match="belongs to another native engine"):
        module.assembly_state_append_occurrence(second, state, template, ("Root",))


def _register_template_source(module: object, handle: object, source: str) -> object:
    snapshot = module.extract_template_snapshot(handle, source, "occurrence_store.py", 1)
    return module.register_template_snapshot(handle, snapshot)


def _engine_with_current_bundle(module: object) -> object:
    handle = module.engine_create()
    module.register_surface_bundle(handle, _surface_bundle_snapshot())
    return handle


def _surface_bundle_snapshot() -> dict[str, object]:
    engine = LowerEngine()
    return engine.surface_registry.register_bundle(current_surface_bundle_spec()).snapshot()


def _index_entry(entries: list[dict[str, object]], key: object) -> dict[str, object]:
    for entry in entries:
        if entry["key"] == key:
            return entry
    raise AssertionError(f"missing index key: {key!r}")
