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
    SELF_NATIVE_SLICE_FEATURES,
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
        missing = missing_self_native_production_features(capabilities)
        assert SELF_NATIVE_CURRENT_SURFACES_FEATURE in missing
        assert missing == tuple(
            feature
            for feature in SELF_NATIVE_SLICE_FEATURES
            if feature not in features
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
    snapshot = production.snapshot()
    assert snapshot["fallback_scope"] == "engine"
    assert snapshot["reason_key"] == "self_native_production_unavailable"
    assert snapshot["requested_engine"] == "auto"
    assert snapshot["selected_engine"] == "python"
    assert "does not advertise required features:" in snapshot["reason_detail"]
    for feature in SELF_NATIVE_SLICE_FEATURES:
        assert feature in snapshot["reason_detail"]


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
                "engine_features": list(SELF_NATIVE_SLICE_FEATURES)
                + [
                    FULL_LOWER_ENGINE_FEATURE,
                    NATIVE_PACKAGE_V2_FEATURE,
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
    assert REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES == SELF_NATIVE_SLICE_FEATURES


def test_built_extension_hybrid_auto_still_selects_native_rust() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    event = select_lower_engine("auto")
    assert event.selected_engine == "native-rust"
