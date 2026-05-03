"""Managed from-import marker collected at module head."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
astichi_pyimport(module=foo, names=(a, b))

result = a() + b()
""",
        file_name="gold_src/pyimport_from_basic.py",
    )


if __name__ == "__main__":
    raise SystemExit(run_case("pyimport_from_basic.py", build_case))
