from __future__ import annotations

from pathlib import Path
import sys

import astichi
import pytest
from astichi.lower_engine import (
    LowerEngine,
    LowerTemplateBinding,
    LowerTemplateCache,
    NativeTemplateCache,
    copy_composable_executable_ast,
    copy_composable_template_ast,
    ensure_current_native_surface_bundle,
    render_composable_source,
)
from astichi.lower_engine.native import load_native_extension
from astichi.structural_snapshot import write_structural_snapshot
from tests.versioned_test_harness import actual_results_dir, data_golden_dir


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STRUCTURAL_GOLDENS_DIR = data_golden_dir(_PROJECT_ROOT, phase="structural")
_ACTUAL_STRUCTURAL_DIR = actual_results_dir(
    _PROJECT_ROOT,
    runtime_version=(sys.version_info.major, sys.version_info.minor),
) / "goldens" / "structural"


def test_compile_registers_lower_template_metadata() -> None:
    composable = astichi.compile(
        """
result = astichi_hole(value)
"""
    )

    lower_template = composable._lower_template

    assert isinstance(lower_template, LowerTemplateBinding)
    assert lower_template.surface_bundle_signature
    assert [
        spec.surface_key for spec in lower_template.record_specs
    ] == [
        "astichi.surface.expression.hole",
        "astichi.surface.block.production",
    ]
    assert all(spec.surface_id is not None for spec in lower_template.record_specs)


def test_compile_lower_template_metadata_matches_structural_golden() -> None:
    composable = astichi.compile(
        """
def make():
    value = astichi_bind_external(default)
    return astichi_hole(result)
"""
    )
    lower_template = composable._lower_template
    assert isinstance(lower_template, LowerTemplateBinding)

    actual_text = write_structural_snapshot(lower_template.structural_snapshot())

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "compile_template_metadata.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "compile_template_metadata.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_compile_explicit_native_attaches_native_template_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    source = "result = astichi_hole(value)\n"
    python_composable = astichi.compile(source)
    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")

    native_composable = astichi.compile(source)

    lower_template = native_composable._lower_template
    assert isinstance(lower_template, LowerTemplateBinding)
    assert lower_template.backend == "native-rust"
    assert lower_template.native_snapshot is not None
    assert lower_template.native_source == source
    assert lower_template.native_origin == native_composable.origin
    assert (
        write_structural_snapshot(lower_template.structural_snapshot())
        == write_structural_snapshot(
            python_composable._lower_template.structural_snapshot()
        )
    )


def test_native_template_cache_reuses_registered_template_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    composable = astichi.compile("result = astichi_hole(value)\n")
    binding = composable._lower_template
    assert isinstance(binding, LowerTemplateBinding)

    engine_handle = module.engine_create()
    cache = NativeTemplateCache(module=module, engine_handle=engine_handle)

    first = cache.template_handle_for(binding)
    second = cache.template_handle_for(binding)

    assert first is second
    assert first.snapshot()["kind"] == "template"
    assert first.snapshot()["index"] == 0

    state = module.assembly_state_create(engine_handle)
    occurrence = module.assembly_state_append_occurrence(
        engine_handle,
        state,
        first,
        ("Root",),
    )
    snapshot = module.assembly_state_snapshot(engine_handle, state)

    assert occurrence.snapshot()["kind"] == "occurrence"
    assert snapshot["templates"][0]["template_key"] == binding.template_key
    assert snapshot["occurrences"] == [
        {
            "build_path": ["Root"],
            "occurrence_id": 0,
            "parent_occurrence_id": None,
            "template_id": 0,
        }
    ]


def test_native_template_cache_rejects_cross_engine_template_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    monkeypatch.setenv("ASTICHI_LOWER_ENGINE", "native")
    binding = astichi.compile("result = astichi_hole(value)\n")._lower_template
    assert isinstance(binding, LowerTemplateBinding)

    first_engine = module.engine_create()
    second_engine = module.engine_create()
    first_cache = NativeTemplateCache(module=module, engine_handle=first_engine)
    ensure_current_native_surface_bundle(
        module=module,
        engine_handle=second_engine,
    )
    first_template = first_cache.template_handle_for(binding)
    second_state = module.assembly_state_create(second_engine)

    with pytest.raises(RuntimeError, match="belongs to another native engine"):
        module.assembly_state_append_occurrence(
            second_engine,
            second_state,
            first_template,
            ("Root",),
        )


def test_compile_funcargs_payload_after_boundary_prefix_uses_payload_locator() -> None:
    composable = astichi.compile(
        """
astichi_pyimport(module=foo, names=(bar,))
astichi_keep(foo)
astichi_funcargs(name__astichi_arg__, key=b)
"""
    )
    lower_template = composable._lower_template
    assert isinstance(lower_template, LowerTemplateBinding)

    assert [
        (
            spec.inventory_kind,
            spec.resource_name,
            spec.ast_path,
            spec.surface_key,
        )
        for spec in lower_template.record_specs
    ] == [
        (
            "identifier.demand",
            "name",
            "body[2]/value/args[0]",
            "astichi.surface.identifier.demand",
        ),
        (
            "production.funcargs",
            "__funcargs__",
            "body[2]/value",
            "astichi.surface.funcargs.production",
        ),
    ]


def test_compile_params_payload_after_boundary_prefix_uses_payload_locator() -> None:
    composable = astichi.compile(
        """
astichi_pyimport(module=foo, names=(bar,))
astichi_keep(foo)
def astichi_params(name__astichi_arg__=1):
    pass
"""
    )
    lower_template = composable._lower_template
    assert isinstance(lower_template, LowerTemplateBinding)

    assert [
        (
            spec.inventory_kind,
            spec.resource_name,
            spec.ast_path,
            spec.surface_key,
        )
        for spec in lower_template.record_specs
    ] == [
        (
            "production.supply",
            "astichi_params",
            "body[2]",
            "astichi.surface.parameter.production",
        ),
        (
            "identifier.demand",
            "name",
            "body[2]/args/args[0]",
            "astichi.surface.identifier.demand",
        ),
    ]


def test_template_binding_rebinds_into_shared_lower_engine() -> None:
    root = astichi.compile("result = astichi_hole(value)\n")
    value = astichi.compile("1\n")
    assert isinstance(root._lower_template, LowerTemplateBinding)
    assert isinstance(value._lower_template, LowerTemplateBinding)
    engine = LowerEngine()
    cache = LowerTemplateCache(engine)

    root_template = cache.template_id_for(root._lower_template)
    value_template = cache.template_id_for(value._lower_template)
    assert cache.template_id_for(root._lower_template) == root_template

    state = engine.new_state()
    engine.append_occurrence(state, root_template, build_path=("Root",))
    engine.append_occurrence(state, value_template, build_path=("Value",))
    actual_text = write_structural_snapshot(engine.structural_snapshot(state))

    _ACTUAL_STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = _ACTUAL_STRUCTURAL_DIR / "shared_template_registration.json"
    actual_path.write_text(actual_text, encoding="utf-8")
    expected_text = (
        _STRUCTURAL_GOLDENS_DIR / "shared_template_registration.json"
    ).read_text(encoding="utf-8")
    assert actual_text == expected_text


def test_explicit_facade_artifact_copy_apis_return_caller_owned_artifacts() -> None:
    composable = astichi.compile("result = 1\n")

    template_ast = copy_composable_template_ast(composable)
    executable_ast = copy_composable_executable_ast(composable)
    source = render_composable_source(composable, provenance=False)

    assert template_ast is not composable.tree
    assert executable_ast is not composable.tree
    assert source == "result = 1\n"
