"""Hatchling build hook: compile and bundle the native lower-engine extension."""

from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ROOT = Path(__file__).resolve().parent
NATIVE_DIR = ROOT / "native_engine"
BUILD_SCRIPT = NATIVE_DIR / "build.py"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _native_artifacts() -> list[Path]:
    abi3 = sorted(
        path
        for path in NATIVE_DIR.glob("_astichi_native_engine*")
        if path.is_file() and "abi3" in path.name
    )
    if abi3:
        return abi3
    return sorted(
        path
        for path in NATIVE_DIR.glob("_astichi_native_engine*")
        if path.is_file()
        and (path.suffix in {".so", ".pyd"} or path.name.endswith(".dll"))
    )


class NativeExtensionBuildHook(BuildHookInterface):
    """Build ``_astichi_native_engine`` and place it at the wheel root."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version != "standard":
            return
        if _env_enabled("ASTICHI_SKIP_NATIVE_BUILD"):
            return
        self._build_and_include_native_extension(build_data)

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        if version != "standard":
            return
        force_include = build_data.get("force_include") or {}
        if not any(
            str(dest).startswith("_astichi_native_engine") for dest in force_include.values()
        ):
            return
        self._retag_platform_wheel(artifact_path)

    def _build_and_include_native_extension(self, build_data: dict[str, Any]) -> None:
        try:
            subprocess.run(
                [sys.executable, str(BUILD_SCRIPT)],
                cwd=ROOT,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            if _env_enabled("ASTICHI_REQUIRE_NATIVE_BUILD"):
                raise RuntimeError(
                    "Astichi native extension build failed. Install a stable Rust "
                    "toolchain or set ASTICHI_SKIP_NATIVE_BUILD=1 for a Python-only "
                    "install."
                ) from exc
            print(
                "warning: Astichi native extension was not built; installing "
                "Python-only (lower engine will fall back to Python).",
                file=sys.stderr,
            )
            return

        artifacts = _native_artifacts()
        if not artifacts:
            if _env_enabled("ASTICHI_REQUIRE_NATIVE_BUILD"):
                raise RuntimeError(
                    "Astichi native extension build produced no installable artifacts"
                )
            return

        force_include = build_data.setdefault("force_include", {})
        for artifact in artifacts:
            force_include[str(artifact)] = artifact.name

    def _retag_platform_wheel(self, wheel_path: str) -> None:
        python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
        artifacts = _native_artifacts()
        if artifacts and "abi3" in artifacts[0].name:
            abi_tag = f"cp{sys.version_info.major}{sys.version_info.minor}-abi3"
        else:
            soabi = sysconfig.get_config_var("SOABI") or python_tag
            abi_tag = soabi.split("-", 1)[0] if soabi.startswith("cp") else python_tag
        platform_tag = sysconfig.get_platform().replace("-", "_").replace(".", "_")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "wheel",
                "tags",
                wheel_path,
                "--remove",
                "--python-tag",
                python_tag,
                "--abi-tag",
                abi_tag,
                "--platform-tag",
                platform_tag,
            ],
            check=True,
        )
