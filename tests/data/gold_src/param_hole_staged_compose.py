"""Staged param-hole composition across ``build()`` boundaries.

Parameter holes are anchor-preserving at ``build()`` time: the authored
parameter stays in ``node.args.args`` and matching
``@astichi_insert(name, kind='params', ref=...)`` shells accumulate as
siblings of the owning ``FunctionDef``. This case pins the contract that
a second builder stage can address into a previously-built root shell's
param hole and merge another contribution in order.
"""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    root = astichi.compile(
        """
def run(params__astichi_param_hole__):
    pass
""",
        file_name="gold_src/param_hole_staged_compose.py",
    )

    stage1_builder = astichi.build()
    stage1_builder.add.Root(root)
    stage1_builder.add.Stage1(
        astichi.compile(
            """
def astichi_params(a):
    pass
""",
            file_name="gold_src/param_hole_staged_compose.py",
        )
    )
    stage1_builder.Root.params.add.Stage1(order=0)
    stage1 = stage1_builder.build()

    stage2_builder = astichi.build()
    stage2_builder.add.Root(stage1)
    stage2_builder.add.Stage2(
        astichi.compile(
            """
def astichi_params(b):
    pass
""",
            file_name="gold_src/param_hole_staged_compose.py",
        )
    )
    stage2_builder.Root.params.add.Stage2(order=1)
    return stage2_builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "params__astichi_param_hole__" in pre_source
    assert "kind='params'" in pre_source
    assert "def run(a, b):" in materialized_source
    assert "astichi_insert" not in materialized_source
    assert "__astichi_param_hole__" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("param_hole_staged_compose.py", build_case, validate_case))
