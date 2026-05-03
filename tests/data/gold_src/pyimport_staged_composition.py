"""Managed imports survive staged composition and child boundary wiring."""

from __future__ import annotations

import astichi
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    stage1 = astichi.build()
    stage1.add.Root(
        astichi.compile(
            """
astichi_pyimport(module=foo, names=(tool,))
astichi_hole(body)
""",
            file_name="gold_src/pyimport_staged_composition.py",
        )
    )
    root = stage1.build()

    stage2 = astichi.build()
    stage2.add.Root(root)
    stage2.add.Child(
        astichi.compile(
            """
astichi_import(tool, outer_bind=True)
result = tool()
""",
            file_name="gold_src/pyimport_staged_composition.py",
        )
    )
    stage2.Root.body.add.Child()
    return stage2.build()


if __name__ == "__main__":
    raise SystemExit(run_case("pyimport_staged_composition.py", build_case))
