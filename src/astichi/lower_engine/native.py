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
from typing import Any


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


def select_lower_engine(value: str | None = None) -> EngineSelectionEvent:
    """Select the lower engine at a coarse boundary without routing behavior."""
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
        missing_features = _missing_required_native_features(capabilities)
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
                reason_key="native_required_features_unavailable",
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
    try:
        return importlib.import_module(EXTENSION_NAME)
    except ImportError:
        dev_dir = _repo_native_engine_dir()
        if dev_dir is None:
            raise
        path_text = str(dev_dir)
        inserted = False
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
            inserted = True
        try:
            return importlib.import_module(EXTENSION_NAME)
        finally:
            if inserted:
                try:
                    sys.path.remove(path_text)
                except ValueError:
                    pass


def _repo_native_engine_dir() -> Path | None:
    repo_root = Path(__file__).resolve().parents[3]
    native_dir = repo_root / "native_engine"
    if native_dir.exists():
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
    features = capabilities.get("engine_features", ())
    available = set(features)
    return tuple(
        feature
        for feature in REQUIRED_NATIVE_LOWER_ENGINE_FEATURES
        if feature not in available
    )


def _native_backend_selection(capabilities: dict[str, Any]) -> str:
    label = str(capabilities.get("backend_label", ""))
    if "cpp" in label or "c++" in label:
        return "native-cpp"
    return "native-rust"
