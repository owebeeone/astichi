"""Sibling roots keep their same-spelled accumulators isolated."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    # First root: two steps import and mutate the same root-owned accumulator.
    builder.add.Root(
        astichi.compile(
            """
total = 0
astichi_hole(body)
result = total
""",
            file_name="gold_src/hygiene_boundary_isolation.py",
        )
    )
    builder.add.Step1(
        astichi.compile(
            """
astichi_import(total)
astichi_bind_external(increment)

total = total + increment
""",
            file_name="gold_src/hygiene_boundary_isolation.py",
        ).bind(increment=1)
    )
    builder.add.Step2(
        astichi.compile(
            """
astichi_import(total)
astichi_bind_external(increment)

total = total + increment
""",
            file_name="gold_src/hygiene_boundary_isolation.py",
        ).bind(increment=2)
    )
    builder.Root.body.add.Step1(order=0)
    builder.Root.body.add.Step2(order=1)
    builder.assign.Step1.total.to().Root.total
    builder.assign.Step2.total.to().Root.total

    # Second root repeats the names; hygiene keeps it isolated from the first.
    builder.add.ARoot(
        astichi.compile(
            """
total = 0
astichi_hole(body)
result = total
""",
            file_name="gold_src/hygiene_boundary_isolation.py",
        )
    )
    builder.add.AStep1(
        astichi.compile(
            """
astichi_import(total)
astichi_bind_external(increment)

total = total + increment
""",
            file_name="gold_src/hygiene_boundary_isolation.py",
        ).bind(increment=10)
    )
    builder.add.AStep2(
        astichi.compile(
            """
astichi_import(total)
astichi_bind_external(increment)

total = total + increment
""",
            file_name="gold_src/hygiene_boundary_isolation.py",
        ).bind(increment=20)
    )
    builder.ARoot.body.add.AStep1(order=0)
    builder.ARoot.body.add.AStep2(order=1)
    builder.assign.AStep1.total.to().ARoot.total
    builder.assign.AStep2.total.to().ARoot.total
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<hygiene_boundary_isolation>")
    result_values = sorted(value for key, value in namespace.items() if key.startswith("result"))
    assert result_values == [3, 30]
    assert "total__astichi_scoped_" in materialized_source
    assert "result__astichi_scoped_" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("hygiene_boundary_isolation.py", build_case, validate_case))
