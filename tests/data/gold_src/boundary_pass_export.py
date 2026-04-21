"""Thread two same-name exports back to distinct root pass sites."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
source_a = 10
source_b = 20
astichi_hole(body)
out_a = astichi_pass(out_a)
out_b = astichi_pass(out_b)
result = (out_a, out_b)
""",
            file_name="gold_src/boundary_pass_export.py",
        )
    )
    builder.add.A(
        astichi.compile(
            """
astichi_import(seed)
out = seed
astichi_export(out)
""",
            file_name="gold_src/boundary_pass_export.py",
        )
    )
    builder.add.B(
        astichi.compile(
            """
astichi_import(seed)
out = seed
astichi_export(out)
""",
            file_name="gold_src/boundary_pass_export.py",
        )
    )
    builder.Root.body.add.A(order=0)
    builder.Root.body.add.B(order=1)
    builder.assign.A.seed.to().Root.source_a
    builder.assign.B.seed.to().Root.source_b
    builder.assign.Root.out_a.to().A.out
    builder.assign.Root.out_b.to().B.out
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<boundary_pass_export>")
    assert namespace["result"] == (10, 20)
    assert "__astichi_assign__inst__A__name__out" in materialized_source
    assert "__astichi_assign__inst__B__name__out" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("boundary_pass_export.py", build_case, validate_case))
