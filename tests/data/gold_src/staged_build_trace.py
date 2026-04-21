"""Three-stage trace recipe: reuse one built composable twice inside another."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    builder1 = astichi.build()
    builder1.add.Root(
        astichi.compile(
            """
astichi_hole(body)
""",
            file_name="gold_src/staged_build_trace.py",
        )
    )
    builder1.add.First(
        astichi.compile(
            """
leaf_tag = "leaf-a"
astichi_pass(trace).append(leaf_tag)
""",
            file_name="gold_src/staged_build_trace.py",
        )
    )
    builder1.add.Second(
        astichi.compile(
            """
leaf_tag = "leaf-b"
astichi_pass(trace).append(leaf_tag)
""",
            file_name="gold_src/staged_build_trace.py",
        )
    )
    builder1.Root.body.add.First(order=0)
    builder1.Root.body.add.Second(order=1)
    composable1 = builder1.build()

    builder2 = astichi.build()
    builder2.add.Middle(
        astichi.compile(
            """
astichi_hole(head)
astichi_hole(tail)
""",
            file_name="gold_src/staged_build_trace.py",
        )
    )
    builder2.add.Head(composable1)
    builder2.add.Tail(composable1)
    builder2.Middle.head.add.Head(order=0)
    builder2.Middle.tail.add.Tail(order=0)
    composable2 = builder2.build()

    builder3 = astichi.build()
    builder3.add.Root(
        astichi.compile(
            """
trace = []
astichi_hole(body)
result = trace
""",
            file_name="gold_src/staged_build_trace.py",
        )
    )
    builder3.add.Pipeline(composable2)
    builder3.Root.body.add.Pipeline(order=0)
    builder3.assign.Pipeline.Middle.trace.to().Root.trace
    return builder3.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<staged_build_trace>")
    assert namespace["result"] == ["leaf-a", "leaf-b", "leaf-a", "leaf-b"]
    assert "leaf_tag__astichi_scoped_" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("staged_build_trace.py", build_case, validate_case))
