from __future__ import annotations

from types import SimpleNamespace

import pytest

from astichi.lower_engine.native import (
    EngineSelectionEvent,
    FULL_LOWER_ENGINE_FEATURE,
    NativeExtensionUnavailableError,
    native_capabilities,
    native_self_test,
    requested_lower_engine,
    select_lower_engine,
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
            "native extension is available but does not advertise "
            f"{FULL_LOWER_ENGINE_FEATURE}"
        ),
        "reason_key": "native_full_lower_engine_unavailable",
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
                "engine_features": [FULL_LOWER_ENGINE_FEATURE],
            },
        ),
    )

    event = select_lower_engine()

    assert event == EngineSelectionEvent(
        requested_engine="auto",
        selected_engine="native-rust",
    )


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
        match="does not advertise native.full_lower_engine",
    ):
        native.select_lower_engine("native")


def test_native_engine_capabilities_when_extension_available() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    assert capabilities["abi_schema_version"] == 1
    assert capabilities["backend_label"] == "rust-pyo3-skeleton"
    assert capabilities["supported_bundle_schema_versions"] == [1]
    assert native_self_test() is True
