"""H4: ``current_surfaces`` implies full self-native production, not hybrid-only native."""

from __future__ import annotations

import pytest

from astichi.lower_engine.native import (
    load_native_extension,
    native_capabilities,
    reset_native_extension_cache,
    select_effective_lower_engine,
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
from astichi.validation.self_native_contract import assert_self_native_production_green
from tests.test_lifecycle_hot_path_python_gate import _run_lifecycle_baseline_subprocess


def test_required_production_features_are_full_self_native_slice() -> None:
    assert REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES == SELF_NATIVE_SLICE_FEATURES
    assert SELF_NATIVE_CURRENT_SURFACES_FEATURE in REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES


def test_current_surfaces_advertised_only_with_full_production_stack() -> None:
    capabilities = native_capabilities()
    if capabilities is None:
        pytest.skip("native engine extension is not built")

    features = capabilities.get("engine_features", ())
    if SELF_NATIVE_CURRENT_SURFACES_FEATURE not in features:
        pytest.skip("capstone feature not advertised on this build")

    missing = missing_self_native_production_features(capabilities)
    assert missing == ()
    assert has_self_native_production(capabilities)


def test_lifecycle_native_uses_self_native_production_selector() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    reset_native_extension_cache()
    if not has_self_native_production(load_native_extension().capabilities()):
        pytest.skip("self-native production stack not advertised")

    event = select_self_native_production_engine("native")
    assert event.selected_engine in {"native-rust", "native-cpp"}
    assert event.fallback_scope is None

    summary = _run_lifecycle_baseline_subprocess()
    selected = summary["selected_lower_engine"]  # type: ignore[index]
    assert selected["selected_engine"] in {"native-rust", "native-cpp"}
    assert selected.get("fallback_scope") is None


def test_effective_selector_matches_production_on_native_request() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    if not has_self_native_production(native_capabilities() or {}):
        pytest.skip("self-native production stack not advertised")

    assert (
        select_effective_lower_engine("native").selected_engine
        == select_self_native_production_engine("native").selected_engine
    )


def test_hybrid_selector_still_available_for_coarse_native() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    assert select_lower_engine("native").selected_engine in {"native-rust", "native-cpp"}


def test_self_native_production_lifecycle_counters_are_green() -> None:
    if load_native_extension(required=False) is None:
        pytest.skip("native engine extension is not built")

    reset_native_extension_cache()
    if not has_self_native_production(load_native_extension().capabilities()):
        pytest.skip("self-native production stack not advertised")

    summary = _run_lifecycle_baseline_subprocess()
    counts = summary["astichi_counters"]["counts"]  # type: ignore[index]
    decorated = int(summary["decorated_classes"])  # type: ignore[arg-type]
    assert_self_native_production_green(counts, decorated_classes=decorated)
