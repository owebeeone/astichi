"""Staged unroll recipe: index per-iteration holes in a later build."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    builder1 = astichi.build()
    builder1.add.Root(
        astichi.compile(
            """
events = []
astichi_hole(body)
result = events
""",
            file_name="gold_src/unroll_literal.py",
        )
    )
    builder1.add.Loop(
        astichi.compile(
            """
astichi_import(events, outer_bind=True)
for x in astichi_for((1, 2, 3)):
    astichi_hole(slot)
""",
            file_name="gold_src/unroll_literal.py",
        )
    )
    builder1.Root.body.add.Loop(order=0)
    composable1 = builder1.build()

    builder2 = astichi.build()
    builder2.add.Pipeline(composable1)
    builder2.add.Step0(
        astichi.compile(
            """
astichi_import(events)
events.append("first")
""",
            file_name="gold_src/unroll_literal.py",
        )
    )
    builder2.Pipeline.Root.Loop.slot[0].add.Step0(order=0)
    builder2.add.Step1(
        astichi.compile(
            """
astichi_import(events, outer_bind=True)
events.append("second")
""",
            file_name="gold_src/unroll_literal.py",
        )
    )
    builder2.Pipeline.Root.Loop.slot[1].add.Step1(order=1)
    builder2.add.Step2(
        astichi.compile(
            """
events = astichi_pass(events, outer_bind=True)
events.append("third")
""",
            file_name="gold_src/unroll_literal.py",
        )
    )
    builder2.Pipeline.Root.Loop.slot[2].add.Step2(order=2)
    builder2.assign.Step0.events.to().Pipeline.Root.events
    return builder2.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "astichi_for" not in materialized_source
    assert "__astichi_assign__inst__Pipeline__ref__Root__name__events.append('first')" in materialized_source
    assert "events.append('second')" in materialized_source
    assert "events__astichi_scoped_" in materialized_source
    assert "append('third')" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("unroll_literal.py", build_case, validate_case))
