"""Self-native production capability contract (full-native roll-build).

Hybrid ``native.full_lower_engine.current_surfaces.v1`` is insufficient for the
YIDL lifecycle production path. Slices advertise per-feature flags in
``engine_features``; production requires ``native.self_native.current_surfaces.v1``.
"""

from __future__ import annotations

from typing import Any

SELF_NATIVE_COMPILE_VALIDATION_FEATURE = "native.self_native.compile_validation.v1"
SELF_NATIVE_NO_PYTHON_PARSE_COMPILE_FEATURE = (
    "native.self_native.no_python_parse_compile.v1"
)
SELF_NATIVE_LITERAL_PAYLOAD_ABI_FEATURE = "native.self_native.literal_payload_abi.v1"
SELF_NATIVE_SCOPE_NO_MIRROR_REPLAY_FEATURE = (
    "native.self_native.scope_no_mirror_replay.v1"
)
SELF_NATIVE_MATERIALIZE_NO_PYTHON_FALLBACK_FEATURE = (
    "native.self_native.materialize_no_python_fallback.v1"
)
SELF_NATIVE_CURRENT_SURFACES_FEATURE = "native.self_native.current_surfaces.v1"

SELF_NATIVE_SLICE_FEATURES: tuple[str, ...] = (
    SELF_NATIVE_LITERAL_PAYLOAD_ABI_FEATURE,
    SELF_NATIVE_SCOPE_NO_MIRROR_REPLAY_FEATURE,
    SELF_NATIVE_COMPILE_VALIDATION_FEATURE,
    SELF_NATIVE_NO_PYTHON_PARSE_COMPILE_FEATURE,
    SELF_NATIVE_MATERIALIZE_NO_PYTHON_FALLBACK_FEATURE,
    SELF_NATIVE_CURRENT_SURFACES_FEATURE,
)

REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES: tuple[str, ...] = (
    SELF_NATIVE_CURRENT_SURFACES_FEATURE,
)


def native_engine_features(capabilities: dict[str, Any]) -> frozenset[str]:
    """Return advertised ``engine_features`` as a set."""
    features = capabilities.get("engine_features", ())
    if not isinstance(features, (list, tuple, set, frozenset)):
        raise TypeError("native capabilities engine_features must be a sequence")
    return frozenset(str(feature) for feature in features)


def missing_self_native_production_features(
    capabilities: dict[str, Any],
) -> tuple[str, ...]:
    """Features required for self-native production but not yet advertised."""
    available = native_engine_features(capabilities)
    return tuple(
        feature
        for feature in REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES
        if feature not in available
    )


def has_self_native_production(capabilities: dict[str, Any]) -> bool:
    """True when the extension advertises the production self-native gate."""
    return not missing_self_native_production_features(capabilities)
