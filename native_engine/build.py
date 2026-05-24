from __future__ import annotations

import importlib.machinery
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


HERE = Path(__file__).resolve().parent
EXTENSION_STEM = "_astichi_native_engine"


def dylib_name() -> str:
    if sys.platform == "darwin":
        return f"lib{EXTENSION_STEM}.dylib"
    if os.name == "nt":
        return f"{EXTENSION_STEM}.dll"
    return f"lib{EXTENSION_STEM}.so"


def main() -> None:
    env = os.environ.copy()
    env["PYO3_PYTHON"] = sys.executable
    if sys.platform == "darwin":
        rustflags = env.get("RUSTFLAGS", "")
        dynamic_lookup = "-C link-arg=-undefined -C link-arg=dynamic_lookup"
        env["RUSTFLAGS"] = f"{rustflags} {dynamic_lookup}".strip()
    subprocess.run(
        ["cargo", "build", "--release", "--manifest-path", str(HERE / "Cargo.toml")],
        check=True,
        cwd=HERE,
        env=env,
    )
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not suffix:
        raise RuntimeError("Python did not report EXT_SUFFIX")
    source = HERE / "target" / "release" / dylib_name()
    targets = [HERE / f"{EXTENSION_STEM}{suffix}"]
    abi3_suffix = next(
        (item for item in importlib.machinery.EXTENSION_SUFFIXES if "abi3" in item),
        None,
    )
    if abi3_suffix:
        targets.append(HERE / f"{EXTENSION_STEM}{abi3_suffix}")
    for target in targets:
        shutil.copy2(source, target)
        print(target)


if __name__ == "__main__":
    main()
