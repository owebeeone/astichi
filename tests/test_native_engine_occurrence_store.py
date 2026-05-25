from __future__ import annotations

import pytest

import astichi
from astichi.assembler import (
    AssemblyScope,
    as_composable,
    as_external_value,
    as_identifier,
    require_one,
)
from astichi.lower_engine import LowerEngine, current_surface_bundle_spec
from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.perf_counters import collect_perf_counters
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


def test_native_candidate_query_finds_composable_expression_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    handle = _engine_with_current_bundle(module)
    root_template = _register_template_source(
        module,
        handle,
        "answer = astichi_hole(value)\n",
    )
    expression_template = _register_template_source(module, handle, "40 + 2\n")
    state = module.assembly_state_create(handle)
    module.assembly_state_append_occurrence(handle, state, root_template, ("Root",))

    result = module.assembly_state_query_composable_candidates(
        handle,
        state,
        expression_template,
        {
            "name": "value",
            "build_match": ["Root"],
            "owner_match": None,
            "target_inventory_kinds": [
                "hole.block",
                "hole.expr",
                "hole.params",
                "hole.elif",
                "hole.positional_variadic",
                "hole.named_variadic",
            ],
            "identifier_bindings": None,
        },
    )

    assert result == {
        "candidates": [
            {
                "production_records": [0],
                "target_record": [0, 0],
            }
        ],
        "diagnostic_summary": {"candidate_count": 1},
    }


def test_native_candidate_query_filters_owner_and_build_selectors_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    handle = _engine_with_current_bundle(module)
    root_template = _register_template_source(
        module,
        handle,
        "class Owner:\n    astichi_hole(body)\n",
    )
    block_template = _register_template_source(module, handle, "value = 1\n")
    state = module.assembly_state_create(handle)
    module.assembly_state_append_occurrence(handle, state, root_template, ("Root",))
    request = {
        "name": "body",
        "build_match": ["Root"],
        "owner_match": ["Owner"],
        "target_inventory_kinds": [
            "hole.block",
            "hole.expr",
            "hole.params",
            "hole.elif",
            "hole.positional_variadic",
            "hole.named_variadic",
        ],
        "identifier_bindings": None,
    }

    matched = module.assembly_state_query_composable_candidates(
        handle,
        state,
        block_template,
        request,
    )
    wrong_owner = module.assembly_state_query_composable_candidates(
        handle,
        state,
        block_template,
        {**request, "owner_match": ["Other"]},
    )
    wrong_build = module.assembly_state_query_composable_candidates(
        handle,
        state,
        block_template,
        {**request, "build_match": ["Other"]},
    )

    assert matched["candidates"] == [
        {
            "production_records": [0],
            "target_record": [0, 0],
        }
    ]
    assert wrong_owner["candidates"] == []
    assert wrong_build["candidates"] == []


def test_native_demand_query_finds_external_and_identifier_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    handle = _engine_with_current_bundle(module)
    root_template = _register_template_source(
        module,
        handle,
        "class class_name__astichi_arg__:\n"
        "    default = astichi_bind_external(default_value)\n",
    )
    state = module.assembly_state_create(handle)
    module.assembly_state_append_occurrence(handle, state, root_template, ("Root",))

    identifier = module.assembly_state_query_demand_candidates(
        handle,
        state,
        {
            "name": "class_name",
            "build_match": ["Root"],
            "owner_match": None,
            "target_inventory_kinds": ["identifier.demand"],
            "identifier_bindings": None,
        },
    )
    external = module.assembly_state_query_demand_candidates(
        handle,
        state,
        {
            "name": "default_value",
            "build_match": ["Root"],
            "owner_match": ["GeneratedClass"],
            "target_inventory_kinds": ["external.bind"],
            "identifier_bindings": [[0, "class_name", "GeneratedClass"]],
        },
    )

    assert identifier["candidates"] == [{"target_record": [0, 0]}]
    assert external["candidates"] == [{"target_record": [0, 1]}]


def test_native_scope_add_routes_root_occurrence_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    scope = AssemblyScope(astichi.build())

    with collect_perf_counters() as counters:
        scope.add("Root", astichi.compile("result = astichi_hole(value)\n"))

    actual = scope.native_lower_structural_snapshot()
    expected = scope.lower_structural_snapshot()
    counts = counters.snapshot()["counts"]

    assert actual == expected
    assert counts["native_scope_append_occurrence"] == 1
    assert counts.get("debug_inventory_projection", 0) == 0


def test_native_scope_composable_lookup_uses_native_query_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("answer = astichi_hole(value)\n")
    expression = astichi.compile("40 + 2\n")
    scope.add("Root", root)

    with collect_perf_counters() as counters:
        candidates = scope.find_candidates(
            as_composable(expression, build_name="Expression"),
            name="value",
            build_match=("Root",),
        )

    candidate = require_one(candidates)
    counts = counters.snapshot()["counts"]

    assert candidate.target_record.build_path.parts == ("Root",)
    assert [record.kind for record in candidate.compatible_productions] == [
        "production.expression",
    ]
    assert counts["candidate_lookup_lower"] == 1
    assert counts["native_candidate_query_composable"] == 1
    assert counts.get("debug_inventory_projection", 0) == 0


def test_native_scope_external_and_identifier_lookup_use_native_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    scope = AssemblyScope(astichi.build())
    root = astichi.compile(
        "class class_name__astichi_arg__:\n"
        "    default = astichi_bind_external(default_value)\n"
    )
    scope.add("Root", root)

    with collect_perf_counters() as identifier_counters:
        identifier = require_one(
            scope.find_candidates(
                as_identifier("GeneratedClass"),
                name="class_name",
                build_match=("Root",),
            )
        )
    scope.apply(identifier)
    with collect_perf_counters() as external_counters:
        external = require_one(
            scope.find_candidates(
                as_external_value(7),
                name="default_value",
                build_match=("Root",),
                owner_match=("GeneratedClass",),
            )
        )

    identifier_counts = identifier_counters.snapshot()["counts"]
    external_counts = external_counters.snapshot()["counts"]

    assert identifier.demand_record.name.logical_name() == "class_name"
    assert external.demand_record.name.logical_name() == "default_value"
    assert str(external.demand_record.code_owner) == "GeneratedClass"
    assert identifier_counts["native_candidate_query_identifier"] == 1
    assert external_counts["native_candidate_query_external"] == 1
    assert external_counts.get("debug_inventory_projection", 0) == 0


def test_native_scope_apply_appends_child_occurrence_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    scope = AssemblyScope(astichi.build())
    root = astichi.compile("answer = astichi_hole(value)\n")
    expression = astichi.compile("40 + 2\n")
    scope.add("Root", root)
    candidate = require_one(
        scope.find_candidates(
            as_composable(expression, build_name="Expression"),
            name="value",
            build_match=("Root",),
        )
    )

    with collect_perf_counters() as counters:
        scope.apply(candidate)

    snapshot = scope.native_lower_structural_snapshot()
    counts = counters.snapshot()["counts"]

    assert snapshot["occurrences"] == [
        {
            "build_path": ["Root"],
            "occurrence_id": 0,
            "parent_occurrence_id": None,
            "template_id": 0,
        },
        {
            "build_path": ["Root", "Expression"],
            "occurrence_id": 1,
            "parent_occurrence_id": 0,
            "template_id": 1,
        },
    ]
    assert counts["native_scope_append_occurrence"] == 1
    assert counts.get("debug_inventory_projection", 0) == 0


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
