"""Expand starred expression holes into tuple and list literals."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
tuple_result = (*astichi_hole(tuple_entries),)
list_result = [*astichi_hole(list_entries)]
""",
            file_name="gold_src/tuple_list_expression_expansion.py",
        )
    )
    builder.add.First(
        astichi.compile(
            """
"first"
""",
            file_name="gold_src/tuple_list_expression_expansion.py",
        )
    )
    builder.add.Second(
        astichi.compile(
            """
"second"
""",
            file_name="gold_src/tuple_list_expression_expansion.py",
        )
    )
    builder.Root.tuple_entries.add.Second(order=1)
    builder.Root.tuple_entries.add.First(order=1)
    builder.Root.list_entries.add.Second(order=1)
    builder.Root.list_entries.add.First(order=0)
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<tuple_list_expression_expansion>")
    assert namespace["tuple_result"] == ("second", "first")
    assert namespace["list_result"] == ["first", "second"]
    assert "astichi_hole" not in materialized_source
    assert "astichi_insert" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(
        run_case("tuple_list_expression_expansion.py", build_case, validate_case)
    )
