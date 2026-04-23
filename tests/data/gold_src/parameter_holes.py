"""Insert function parameters and bind body snippets to the expanded signature."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    params_builder = astichi.build()
    params_builder.add.Params(
        astichi.compile(
            """
def astichi_params(
    session,
    limit: astichi_hole(limit_type) = 5,
    *items,
    debug=False,
    **options,
):
    pass
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    params_builder.add.Type(
        astichi.compile(
            """
int
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    params_builder.Params.limit_type.add.Type()

    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def run(params__astichi_param_hole__):
    astichi_hole(body)
    return session
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    builder.add.Params(params_builder.build())
    builder.add.BodyUsesParam(
        astichi.compile(
            """
value = astichi_pass(session, outer_bind=True)
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    builder.add.BodyLocalCollision(
        astichi.compile(
            """
session = "local"
local_session = session
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    builder.Root.params.add.Params(order=0)
    builder.Root.body.add.BodyUsesParam(order=0)
    builder.Root.body.add.BodyLocalCollision(order=1)
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "kind='params'" in pre_source
    assert "params__astichi_param_hole__" in pre_source
    assert "def run(session, limit: int=5, *items, debug=False, **options):" in materialized_source
    assert "value = session" in materialized_source
    assert "session__astichi_scoped_" in materialized_source
    assert "astichi_insert" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("parameter_holes.py", build_case, validate_case))
