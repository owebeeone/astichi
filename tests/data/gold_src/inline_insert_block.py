"""Two ordered block inserts append into a root-owned list."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
items = []
astichi_hole(body)
result = items
""",
            file_name="gold_src/inline_insert_block.py",
        )
    )
    builder.add.First(
        astichi.compile(
            """
astichi_pass(items, outer_bind=True).append("first")
""",
            file_name="gold_src/inline_insert_block.py",
        )
    )
    builder.add.Second(
        astichi.compile(
            """
astichi_pass(items, outer_bind=True).append("second")
""",
            file_name="gold_src/inline_insert_block.py",
        )
    )
    builder.Root.body.add.Second(order=1)
    builder.Root.body.add.First(order=0)
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<inline_insert_block>")
    assert namespace["result"] == ["first", "second"]


if __name__ == "__main__":
    raise SystemExit(run_case("inline_insert_block.py", build_case, validate_case))
