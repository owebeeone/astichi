"""Managed from-import from an ordinary dotted module reference."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
astichi_pyimport(module=package.submodule, names=(thing,))

result = thing()
""",
        file_name="gold_src/pyimport_dotted_module.py",
    )


if __name__ == "__main__":
    raise SystemExit(run_case("pyimport_dotted_module.py", build_case))
