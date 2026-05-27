"""Shared native engine for hot-path template compile (H2).

Registers templates once per source into a process-local native engine instead
of extracting throwaway package-v2 PyDict snapshots per ``astichi.compile`` call.
"""

from __future__ import annotations

from types import ModuleType

from astichi.model import CompileOrigin

_registry: tuple[ModuleType, object] | None = None


def shared_hot_path_native_engine(module: ModuleType) -> object:
    """Return the process-local native engine used for hot-path compile registration."""
    global _registry
    if _registry is None:
        from astichi.lower_engine.facade import _current_surface_bundle_snapshot

        handle = module.engine_create()
        module.register_surface_bundle(handle, _current_surface_bundle_snapshot())
        _registry = (module, handle)
    return _registry[1]


def register_hot_path_template_source(
    module: ModuleType,
    *,
    source: str,
    origin: CompileOrigin,
) -> object:
    """Register ``source`` in the shared hot-path engine and return a template handle."""
    engine = shared_hot_path_native_engine(module)
    return module.register_template_package_v2_source(
        engine,
        source,
        origin.file_name,
        origin.line_number,
    )


def reset_hot_path_native_registry_for_tests() -> None:
    """Close and clear the shared hot-path engine (tests only)."""
    global _registry
    if _registry is None:
        return
    module, handle = _registry
    try:
        module.engine_close(handle)
    finally:
        _registry = None
