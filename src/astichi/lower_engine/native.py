"""Production native lower-engine discovery.

The default engine request is ``auto``. This module only owns discovery and
selection metadata until a future slice routes lower-engine behavior natively.
An importable skeleton is not selected as native unless it advertises the full
lower-engine capability set.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Literal

from astichi.lower_engine.self_native import (
    REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES,
    has_self_native_production,
)


EXTENSION_NAME = "_astichi_native_engine"
ENGINE_SELECTION_ENV = "ASTICHI_LOWER_ENGINE"
DEFAULT_ENGINE = "auto"
FULL_LOWER_ENGINE_FEATURE = "native.full_lower_engine.current_surfaces.v1"
NATIVE_PACKAGE_V2_FEATURE = "native.lower_template_package_v2.v1"
REQUIRED_NATIVE_LOWER_ENGINE_FEATURES = (
    FULL_LOWER_ENGINE_FEATURE,
    NATIVE_PACKAGE_V2_FEATURE,
)
VALID_ENGINE_SELECTIONS = frozenset(
    {"python", "native", "native-rust", "native-cpp", "auto"}
)


class NativeExtensionUnavailableError(RuntimeError):
    """Raised when explicit native selection cannot load the extension."""


@dataclass(frozen=True, slots=True)
class EngineSelectionEvent:
    requested_engine: str
    selected_engine: str
    fallback_scope: str | None = None
    reason_key: str | None = None
    reason_detail: str | None = None

    def snapshot(self) -> dict[str, str | None]:
        return {
            "requested_engine": self.requested_engine,
            "selected_engine": self.selected_engine,
            "fallback_scope": self.fallback_scope,
            "reason_key": self.reason_key,
            "reason_detail": self.reason_detail,
        }


_native_cache: ModuleType | None | bool = False


def reset_native_extension_cache() -> None:
    """Clear the import cache so the next load re-resolves the extension module."""
    global _native_cache
    _native_cache = False
    sys.modules.pop(EXTENSION_NAME, None)


def requested_lower_engine(value: str | None = None) -> str:
    """Normalize an explicit or environment-provided lower-engine request."""
    requested = value or os.environ.get(ENGINE_SELECTION_ENV, DEFAULT_ENGINE)
    if requested not in VALID_ENGINE_SELECTIONS:
        allowed = ", ".join(sorted(VALID_ENGINE_SELECTIONS))
        raise ValueError(
            f"unknown lower engine {requested!r}; expected one of: {allowed}"
        )
    return requested


def load_native_extension(*, required: bool = False) -> ModuleType | None:
    """Load the native extension if it is available."""
    global _native_cache
    if isinstance(_native_cache, ModuleType):
        return _native_cache
    if _native_cache is None:
        if required:
            raise NativeExtensionUnavailableError(
                "Astichi native engine extension is not available"
            )
        return None
    try:
        _native_cache = _import_native_extension()
    except ImportError as exc:
        _native_cache = None
        if required:
            raise NativeExtensionUnavailableError(
                "Astichi native engine extension is not available; run "
                "`uv run python native_engine/build.py` from the Astichi repo"
            ) from exc
        return None
    return _native_cache


def native_capabilities() -> dict[str, Any] | None:
    """Return native capabilities, or ``None`` when the extension is absent."""
    module = load_native_extension(required=False)
    if module is None:
        return None
    return _native_capability_snapshot(module)


def native_self_test() -> bool | None:
    """Run the native self-test when available."""
    module = load_native_extension(required=False)
    if module is None:
        return None
    return bool(module.self_test())


def lower_engine_tier(capabilities: dict[str, Any]) -> Literal["hybrid", "self_native"]:
    """Classify native extension tier for diagnostics and production guards."""
    if has_self_native_production(capabilities):
        return "self_native"
    return "hybrid"


def select_lower_engine(value: str | None = None) -> EngineSelectionEvent:
    """Select the hybrid/native lower engine at a coarse boundary.

    This remains the lifecycle default until ``native.self_native.current_surfaces.v1``
    is advertised. Use :func:`select_self_native_production_engine` for the
    full self-native production gate.
    """
    return _select_native_tier_engine(
        value,
        required_features=REQUIRED_NATIVE_LOWER_ENGINE_FEATURES,
        unavailable_reason_key="native_required_features_unavailable",
    )


def select_self_native_production_engine(
    value: str | None = None,
) -> EngineSelectionEvent:
    """Select the engine for the YIDL lifecycle production path.

    Explicit ``native`` without self-native capabilities fails with a diagnostic
    instead of silently using the hybrid native path.
    """
    return _select_native_tier_engine(
        value,
        required_features=REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES,
        unavailable_reason_key="self_native_production_unavailable",
    )


def _select_native_tier_engine(
    value: str | None,
    *,
    required_features: tuple[str, ...],
    unavailable_reason_key: str,
) -> EngineSelectionEvent:
    requested = requested_lower_engine(value)
    if requested == "python":
        return EngineSelectionEvent(
            requested_engine=requested,
            selected_engine="python",
        )

    module = load_native_extension(required=False)
    if module is not None:
        capabilities = _native_capability_snapshot(module)
        selected = _native_backend_selection(capabilities)
        if requested not in {"native", "auto", selected}:
            raise NativeExtensionUnavailableError(
                f"requested {requested!r}, but the available native backend "
                f"is {selected!r}"
            )
        missing_features = _missing_features(capabilities, required_features)
        if not missing_features:
            return EngineSelectionEvent(
                requested_engine=requested,
                selected_engine=selected,
            )
        reason = (
            "native extension is available but does not advertise required "
            f"features: {', '.join(missing_features)}"
        )
        if requested == "auto":
            return EngineSelectionEvent(
                requested_engine=requested,
                selected_engine="python",
                fallback_scope="engine",
                reason_key=unavailable_reason_key,
                reason_detail=reason,
            )
        raise NativeExtensionUnavailableError(
            f"requested {requested!r}, but {reason}"
        )

    if requested == "auto":
        return EngineSelectionEvent(
            requested_engine=requested,
            selected_engine="python",
            fallback_scope="engine",
            reason_key="native_extension_unavailable",
            reason_detail="native extension is not built or importable",
        )

    raise NativeExtensionUnavailableError(
        "Astichi native engine extension is not available; run "
        "`uv run python native_engine/build.py` from the Astichi repo"
    )


def _import_native_extension() -> ModuleType:
    dev_dir = _repo_native_engine_dir()
    if dev_dir is not None:
        path_text = str(dev_dir)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
        try:
            return importlib.import_module(EXTENSION_NAME)
        except ImportError:
            pass
    return importlib.import_module(EXTENSION_NAME)


def _repo_native_engine_dir() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        native_dir = parent / "native_engine"
        if (native_dir / "Cargo.toml").exists():
            return native_dir
    return None


def _native_capability_snapshot(module: ModuleType) -> dict[str, Any]:
    capabilities = module.capabilities()
    if not isinstance(capabilities, dict):
        raise TypeError("native capabilities must be a dict")
    return dict(capabilities)


def _missing_required_native_features(
    capabilities: dict[str, Any],
) -> tuple[str, ...]:
    return _missing_features(capabilities, REQUIRED_NATIVE_LOWER_ENGINE_FEATURES)


def _missing_features(
    capabilities: dict[str, Any],
    required: tuple[str, ...],
) -> tuple[str, ...]:
    features = capabilities.get("engine_features", ())
    available = set(features)
    return tuple(feature for feature in required if feature not in available)


def _native_backend_selection(capabilities: dict[str, Any]) -> str:
    label = str(capabilities.get("backend_label", ""))
    if "cpp" in label or "c++" in label:
        return "native-cpp"
    return "native-rust"
