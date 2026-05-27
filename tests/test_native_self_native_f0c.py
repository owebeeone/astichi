from __future__ import annotations

from types import SimpleNamespace

import pytest

from astichi.lower_engine.native import (
    FULL_LOWER_ENGINE_FEATURE,
    NATIVE_PACKAGE_V2_FEATURE,
    NativeExtensionUnavailableError,
    load_native_extension,
    lower_engine_tier,
    native_capabilities,
    select_lower_engine,
    select_self_native_production_engine,
)
from astichi.lower_engine.self_native import (
    REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES,
    SELF_NATIVE_CURRENT_SURFACES_FEATURE,
    has_self_native_production,
    missing_self_native_production_features,
)


def test_built_extension_self_native_tier_matches_current_surfaces_cap() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    features = capabilities.get("engine_features", ())
    if SELF_NATIVE_CURRENT_SURFACES_FEATURE not in features:
        assert lower_engine_tier(capabilities) == "hybrid"
        assert has_self_native_production(capabilities) is False
        assert missing_self_native_production_features(capabilities) == (
            SELF_NATIVE_CURRENT_SURFACES_FEATURE,
        )
        return

    assert lower_engine_tier(capabilities) == "self_native"
    assert has_self_native_production(capabilities) is True
    assert missing_self_native_production_features(capabilities) == ()


def test_hybrid_caps_satisfy_select_lower_engine_not_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

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

    assert select_lower_engine("auto").selected_engine == "native-rust"

    production = select_self_native_production_engine("auto")
    assert production.snapshot() == {
        "fallback_scope": "engine",
        "reason_detail": (
            "native extension is available but does not advertise required "
            f"features: {SELF_NATIVE_CURRENT_SURFACES_FEATURE}"
        ),
        "reason_key": "self_native_production_unavailable",
        "requested_engine": "auto",
        "selected_engine": "python",
    }


def test_explicit_native_production_fails_for_hybrid_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

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

    select_lower_engine("native")

    with pytest.raises(
        NativeExtensionUnavailableError,
        match=SELF_NATIVE_CURRENT_SURFACES_FEATURE,
    ):
        select_self_native_production_engine("native")


def test_self_native_production_selects_when_cap_advertised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astichi.lower_engine.native as native

    monkeypatch.setattr(
        native,
        "load_native_extension",
        lambda *, required=False: SimpleNamespace(
            capabilities=lambda: {
                "backend_label": "rust-pyo3-lower-engine",
                "engine_features": [
                    FULL_LOWER_ENGINE_FEATURE,
                    NATIVE_PACKAGE_V2_FEATURE,
                    SELF_NATIVE_CURRENT_SURFACES_FEATURE,
                ],
            },
        ),
    )

    capabilities = native.load_native_extension().capabilities()
    assert lower_engine_tier(capabilities) == "self_native"
    assert has_self_native_production(capabilities) is True

    event = select_self_native_production_engine("auto")
    assert event == native.EngineSelectionEvent(
        requested_engine="auto",
        selected_engine="native-rust",
    )


def test_required_self_native_production_features_tuple() -> None:
    assert REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES == (
        SELF_NATIVE_CURRENT_SURFACES_FEATURE,
    )


def test_built_extension_hybrid_auto_still_selects_native_rust() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    event = select_lower_engine("auto")
    assert event.selected_engine == "native-rust"
