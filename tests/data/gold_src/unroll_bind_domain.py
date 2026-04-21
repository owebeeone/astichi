"""Bind an unroll domain before wiring indexed iteration holes."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            """
astichi_bind_external(VALUES)
for value in astichi_for(VALUES):
    astichi_hole(slot)
""",
            file_name="gold_src/unroll_bind_domain.py",
        ).bind(VALUES=[7, 9])
    )
    builder.add.B0(
        astichi.compile(
            """
first = 7
""",
            file_name="gold_src/unroll_bind_domain.py",
        )
    )
    builder.add.B1(
        astichi.compile(
            """
second = 9
""",
            file_name="gold_src/unroll_bind_domain.py",
        )
    )
    builder.A.slot[0].add.B0()
    builder.A.slot[1].add.B1()
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "astichi_for" not in materialized_source
    assert "first = 7" in materialized_source
    assert "second = 9" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("unroll_bind_domain.py", build_case, validate_case))
