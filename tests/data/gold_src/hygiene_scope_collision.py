"""Show hygiene renaming when inserted code reuses an outer local name."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
value = 1
astichi_hole(body)
result_outer = astichi_keep(value)
""",
            file_name="gold_src/hygiene_scope_collision.py",
        )
    )
    builder.add.Inner(
        astichi.compile(
            """
value = 2
result_inner = value
""",
            file_name="gold_src/hygiene_scope_collision.py",
        )
    )
    builder.Root.body.add.Inner(order=0)
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "value__astichi_scoped_" in materialized_source
    assert "result_outer = value" in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("hygiene_scope_collision.py", build_case, validate_case))
