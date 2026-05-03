"""Managed import aliases when hygiene renames the local binding."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    return astichi.compile(
        """
a = 1
astichi_hole(slot)

@astichi_insert(slot)
def shell():
    astichi_pyimport(module=foo, names=(a,))
    result = a()
""",
        file_name="gold_src/pyimport_hygiene_collision.py",
        source_kind="astichi-emitted",
    )


if __name__ == "__main__":
    raise SystemExit(run_case("pyimport_hygiene_collision.py", build_case))
