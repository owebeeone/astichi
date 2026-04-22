"""Show dict expansion entries from separate snippets keep separate scopes."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
result = {**astichi_hole(entries)}
""",
            file_name="gold_src/dict_expansion_hygiene.py",
        )
    )
    builder.add.Left(
        astichi.compile(
            """
{(value := 1): value}
""",
            file_name="gold_src/dict_expansion_hygiene.py",
        )
    )
    builder.add.Right(
        astichi.compile(
            """
{1: (value := 2, value)}
""",
            file_name="gold_src/dict_expansion_hygiene.py",
        )
    )
    builder.Root.entries.add.Left(order=0)
    builder.Root.entries.add.Right(order=1)
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "value__astichi_scoped_" in materialized_source
    assert "result = {(value := 1): value, 1:" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("dict_expansion_hygiene.py", build_case, validate_case))
