"""Native compile-time validation entrypoints (F3b)."""

from __future__ import annotations

from astichi.lower_engine.native import load_native_extension, native_capabilities
from astichi.lower_engine.self_native import SELF_NATIVE_COMPILE_VALIDATION_FEATURE
from astichi.perf_counters import active_perf_counters


def native_compile_validation_enabled() -> bool:
    capabilities = native_capabilities()
    if capabilities is None:
        return False
    features = capabilities.get("engine_features", ())
    return SELF_NATIVE_COMPILE_VALIDATION_FEATURE in features


def native_compile_validate_source(
    source: str,
    *,
    file_name: str | None = None,
) -> None:
    """Run native compile validators on authored source text."""
    module = load_native_extension(required=True)
    assert module is not None
    counters = active_perf_counters()
    if counters is None:
        module.compile_validate_source(source, file_name)
        return
    with counters.measure("native_compile_validate_source"):
        module.compile_validate_source(source, file_name)
