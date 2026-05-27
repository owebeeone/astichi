from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from astichi.lower_engine import (
    LowerEngine,
    PYTHON_PACKAGE_ONLY_PLAN_FEATURE,
    PYTHON_PACKAGE_V2_FEATURE,
    current_plus_future_surface_bundle_spec,
    current_surface_bundle_spec,
)
from astichi.lower_engine.native import (
    EngineSelectionEvent,
    FULL_LOWER_ENGINE_FEATURE,
    NATIVE_PACKAGE_V2_FEATURE,
    NativeExtensionUnavailableError,
    REQUIRED_NATIVE_LOWER_ENGINE_FEATURES,
    load_native_extension,
    native_capabilities,
    native_self_test,
    requested_lower_engine,
    reset_native_extension_cache,
    select_lower_engine,
)
from astichi.lower_engine.self_native import (
    SELF_NATIVE_LITERAL_PAYLOAD_ABI_FEATURE,
    SELF_NATIVE_SCOPE_NO_MIRROR_REPLAY_FEATURE,
)


def test_native_engine_default_request_is_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASTICHI_LOWER_ENGINE", raising=False)

    assert requested_lower_engine() == "auto"


def test_native_engine_default_selection_falls_back_for_skeleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

    monkeypatch.delenv("ASTICHI_LOWER_ENGINE", raising=False)
    monkeypatch.setattr(
        native,
        "load_native_extension",
        lambda *, required=False: SimpleNamespace(
            capabilities=lambda: {
                "backend_label": "rust-pyo3-skeleton",
                "engine_features": [],
            },
        ),
    )

    event = select_lower_engine()

    assert event.snapshot() == {
        "fallback_scope": "engine",
        "reason_detail": (
            "native extension is available but does not advertise required "
            "features: "
            + ", ".join(REQUIRED_NATIVE_LOWER_ENGINE_FEATURES)
        ),
        "reason_key": "native_required_features_unavailable",
        "requested_engine": "auto",
        "selected_engine": "python",
    }


def test_native_engine_default_selection_prefers_capable_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

    monkeypatch.delenv("ASTICHI_LOWER_ENGINE", raising=False)
    monkeypatch.setattr(
        native,
        "load_native_extension",
        lambda *, required=False: SimpleNamespace(
            capabilities=lambda: {
                "backend_label": "rust-pyo3-lower-engine",
                "engine_features": [
                    FULL_LOWER_ENGINE_FEATURE,
                    NATIVE_PACKAGE_V2_FEATURE,
                ],
            },
        ),
    )

    event = select_lower_engine()

    assert event == EngineSelectionEvent(
        requested_engine="auto",
        selected_engine="native-rust",
    )


def test_native_engine_default_selection_falls_back_without_package_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

    monkeypatch.delenv("ASTICHI_LOWER_ENGINE", raising=False)
    monkeypatch.setattr(
        native,
        "load_native_extension",
        lambda *, required=False: SimpleNamespace(
            capabilities=lambda: {
                "backend_label": "rust-pyo3-lower-engine",
                "engine_features": [FULL_LOWER_ENGINE_FEATURE],
            },
        ),
    )

    event = select_lower_engine()

    assert event.snapshot() == {
        "fallback_scope": "engine",
        "reason_detail": (
            "native extension is available but does not advertise required "
            f"features: {NATIVE_PACKAGE_V2_FEATURE}"
        ),
        "reason_key": "native_required_features_unavailable",
        "requested_engine": "auto",
        "selected_engine": "python",
    }


def test_native_engine_default_selection_falls_back_without_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

    monkeypatch.delenv("ASTICHI_LOWER_ENGINE", raising=False)
    monkeypatch.setattr(native, "load_native_extension", lambda *, required=False: None)

    event = native.select_lower_engine()

    assert event.snapshot() == {
        "fallback_scope": "engine",
        "reason_detail": "native extension is not built or importable",
        "reason_key": "native_extension_unavailable",
        "requested_engine": "auto",
        "selected_engine": "python",
    }


def test_native_engine_rejects_unknown_selection() -> None:
    with pytest.raises(ValueError, match="unknown lower engine"):
        requested_lower_engine("native-fortran")


def test_native_engine_auto_falls_back_when_extension_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

    monkeypatch.setattr(native, "load_native_extension", lambda *, required=False: None)

    event = native.select_lower_engine("auto")

    assert event.snapshot() == {
        "fallback_scope": "engine",
        "reason_detail": "native extension is not built or importable",
        "reason_key": "native_extension_unavailable",
        "requested_engine": "auto",
        "selected_engine": "python",
    }


def test_native_engine_explicit_native_fails_when_extension_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

    monkeypatch.setattr(native, "load_native_extension", lambda *, required=False: None)

    with pytest.raises(NativeExtensionUnavailableError):
        native.select_lower_engine("native")


def test_native_engine_explicit_native_fails_for_skeleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

    monkeypatch.setattr(
        native,
        "load_native_extension",
        lambda *, required=False: SimpleNamespace(
            capabilities=lambda: {
                "backend_label": "rust-pyo3-skeleton",
                "engine_features": [],
            },
        ),
    )

    with pytest.raises(
        NativeExtensionUnavailableError,
        match="does not advertise required features",
    ):
        native.select_lower_engine("native")


def test_python_lower_engine_capabilities_advertise_package_v2() -> None:
    capabilities = LowerEngine().capabilities()

    assert capabilities["lower_template_package_v2"] is True
    assert capabilities["engine_features"] == [
        PYTHON_PACKAGE_V2_FEATURE,
        PYTHON_PACKAGE_ONLY_PLAN_FEATURE,
    ]


def test_native_engine_capabilities_when_extension_available() -> None:
    reset_native_extension_cache()
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    assert capabilities["abi_schema_version"] == 1
    assert capabilities["backend_label"] == "rust-pyo3-core"
    features = capabilities["engine_features"]
    if SELF_NATIVE_LITERAL_PAYLOAD_ABI_FEATURE not in features:
        pytest.skip(
            "rebuild native_engine for F1b capabilities "
            "(uv run python native_engine/build.py)"
        )
    assert SELF_NATIVE_SCOPE_NO_MIRROR_REPLAY_FEATURE in features
    assert capabilities["engine_features"] == [
        "native.extension.v1",
        "native.engine_core.v1",
        "native.parser_ir.v1",
        "native.surface_registry.v1",
        "native.pattern_registry.v1",
        "native.template_snapshot.empty.v1",
        "native.template_extract.direct_call.v1",
        "native.template_extract.identifier_suffix.v1",
        "native.template_extract.payload.v1",
        "native.template_extract.insert_metadata.v1",
        "native.occurrence_store.v1",
        "native.record_indexes.v1",
        "native.candidate_query.v1",
        "native.overlay_store.v1",
        "native.materialization_operation_stream.v1",
        "native.materialization_overlay_stream.v1",
        "native.materialization_workspace.v1",
        "native.materialization_expression.v1",
        "native.materialization_block.v1",
        "native.materialization_parameters.v1",
        "native.materialization_call_arguments.v1",
        "native.materialization_identifier_overlay.v1",
        "native.materialization_literal_ref.v1",
        "native.materialization_external_overlay_literal.v1",
        "native.hygiene_gate.v1",
        "native.artifact_builder.python_ast.baseline.v1",
        "native.lower_template_package_v2.snapshot.partial.v1",
        "native.lower_template_package_v2.v1",
        "native.full_lower_engine.current_surfaces.v1",
        "native.self_native.literal_payload_abi.v1",
        "native.self_native.scope_no_mirror_replay.v1",
    ]
    assert capabilities["artifact_kinds"] == ["python_ast"]
    assert capabilities["supported_bundle_schema_versions"] == [1]
    assert native_self_test() is True


def test_native_engine_core_handle_lifecycle_when_extension_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    handle = module.engine_create()
    snapshot = module.engine_snapshot(handle)

    assert snapshot["engine_epoch"] == 1
    assert snapshot["kind"] == "engine"
    assert snapshot["index"] == 0
    assert snapshot["generation"] == 0
    assert snapshot["closed"] is False
    assert handle.snapshot() == snapshot

    module.engine_close(handle)
    assert handle.closed is True
    assert handle.generation == 1
    with pytest.raises(RuntimeError, match="native stale handle"):
        module.engine_snapshot(handle)


def test_native_engine_core_rejects_cross_engine_handles_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    first = module.engine_create()
    second = module.engine_create()

    with pytest.raises(RuntimeError, match="belongs to another native engine"):
        module.engine_assert_same_owner(first, second)


def test_native_engine_core_rejects_bad_create_request_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    with pytest.raises(ValueError, match="native schema error"):
        module.engine_create("not-a-request-dict")


def test_native_engine_auto_selects_capable_extension_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    event = select_lower_engine("auto")

    assert event.snapshot() == {
        "fallback_scope": None,
        "reason_detail": None,
        "reason_key": None,
        "requested_engine": "auto",
        "selected_engine": "native-rust",
    }


def test_native_surface_registry_matches_current_bundle_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    expected = _surface_bundle_snapshot(current_surface_bundle_spec())
    handle = module.engine_create()

    actual = module.register_surface_bundle(handle, expected)

    assert actual == expected
    assert module.surface_bundle_snapshot(handle) == expected
    snapshot = module.engine_snapshot(handle)
    assert snapshot["surface_bundle_registered"] is True
    assert snapshot["surface_count"] == len(expected["surfaces"])
    assert snapshot["operation_count"] == len(expected["operations"])
    assert snapshot["pattern_count"] == len(expected["patterns"])


def test_native_surface_registry_matches_future_bundle_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    expected = _surface_bundle_snapshot(current_plus_future_surface_bundle_spec())
    handle = module.engine_create()

    actual = module.register_surface_bundle(handle, expected)

    assert actual == expected
    assert any(not pattern["enabled"] for pattern in actual["patterns"])


def test_native_surface_registry_rejects_duplicate_keys_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    bad = deepcopy(_surface_bundle_snapshot(current_surface_bundle_spec()))
    bad["surfaces"].append(dict(bad["surfaces"][0]))

    with pytest.raises(ValueError, match="duplicate surface keys"):
        module.register_surface_bundle(module.engine_create(), bad)


def test_native_surface_registry_rejects_unknown_pattern_refs_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    bad = deepcopy(_surface_bundle_snapshot(current_surface_bundle_spec()))
    bad["patterns"][0]["surface_key"] = "astichi.surface.missing"

    with pytest.raises(ValueError, match="pattern references unknown surface"):
        module.register_surface_bundle(module.engine_create(), bad)


def test_native_surface_registry_rejects_second_bundle_when_available() -> None:
    module = load_native_extension(required=False)
    if module is None:
        pytest.skip("native engine extension is not built")

    snapshot = _surface_bundle_snapshot(current_surface_bundle_spec())
    handle = module.engine_create()
    module.register_surface_bundle(handle, snapshot)

    with pytest.raises(ValueError, match="surface bundle is already registered"):
        module.register_surface_bundle(handle, snapshot)


def _surface_bundle_snapshot(spec: object) -> dict[str, object]:
    engine = LowerEngine()
    return engine.surface_registry.register_bundle(spec).snapshot()
