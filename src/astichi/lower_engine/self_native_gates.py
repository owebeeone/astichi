"""Runtime checks for advertised self-native slice capabilities."""

from __future__ import annotations

from astichi.lower_engine.native import native_capabilities
from astichi.lower_engine.self_native import (
    SELF_NATIVE_MATERIALIZE_NO_PYTHON_FALLBACK_FEATURE,
)


def native_materialize_no_python_fallback_enabled() -> bool:
    capabilities = native_capabilities()
    if capabilities is None:
        return False
    features = capabilities.get("engine_features", ())
    return SELF_NATIVE_MATERIALIZE_NO_PYTHON_FALLBACK_FEATURE in features
