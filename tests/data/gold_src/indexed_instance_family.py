"""Register indexed builder instances and wire one of them later by name."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
result = []
astichi_hole(body)
final = tuple(result)
""",
            file_name="gold_src/indexed_instance_family.py",
        )
    )

    builder.add.Step[0](
        astichi.compile(
            """
result.append("step-0")
""",
            file_name="gold_src/indexed_instance_family.py",
        )
    )
    builder.add.Step[1](
        astichi.compile(
            """
result.append("step-1")
astichi_hole(extra)
""",
            file_name="gold_src/indexed_instance_family.py",
        )
    )
    builder.add.Step[2](
        astichi.compile(
            """
result.append("step-2")
""",
            file_name="gold_src/indexed_instance_family.py",
        )
    )
    builder.add.Helper(
        astichi.compile(
            """
astichi_pass(result, outer_bind=True).append("step-1-extra")
""",
            file_name="gold_src/indexed_instance_family.py",
        )
    )

    builder.Root.body.add.Step[0](order=0)
    builder.Root.body.add.Step[1](order=1)
    builder.Root.body.add.Step[2](order=2)
    builder.Step[1].extra.add.Helper(order=0)
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<indexed_instance_family>")
    assert namespace["final"] == ("step-0", "step-1", "step-1-extra", "step-2")
    assert "step-1-extra" in materialized_source
    assert "astichi_hole" not in materialized_source
    assert "astichi_insert" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("indexed_instance_family.py", build_case, validate_case))
