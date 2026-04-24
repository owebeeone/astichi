"""Re-add a built source twice with different edge-local identifier overlays."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    stage1 = astichi.build()
    stage1.add.Root(
        astichi.compile(
            """
astichi_hole(body)
""",
            file_name="gold_src/edge_multibind_staged.py",
        )
    )
    stage1.add.Step(
        astichi.compile(
            """
astichi_pass(records, outer_bind=True).append(
    astichi_pass(name, outer_bind=True)
)
""",
            file_name="gold_src/edge_multibind_staged.py",
        )
    )
    stage1.Root.body.add.Step(order=0)
    pipeline = stage1.build()

    stage2 = astichi.build()
    stage2.add.Root(
        astichi.compile(
            """
left = 10
right = 20
records = []
astichi_hole(body)
result = records
""",
            file_name="gold_src/edge_multibind_staged.py",
        )
    )
    stage2.add.Pipeline(pipeline)
    stage2.Root.body.add.Pipeline(order=0, arg_names={"name": "left"})
    stage2.Root.body.add.Pipeline(order=1, arg_names={"name": "right"})
    return stage2.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<edge_multibind_staged>")
    assert namespace["result"] == [10, 20]
    assert "__astichi_arg__" not in materialized_source
    assert "astichi_insert" not in materialized_source
    assert "astichi_hole" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(
        run_case("edge_multibind_staged.py", build_case, validate_case)
    )
