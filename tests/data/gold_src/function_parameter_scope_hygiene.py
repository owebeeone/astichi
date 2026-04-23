"""Function parameter names stay local to their Python function scope."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
astichi_hole(body)

def owns_param(token):
    astichi_hole(inner)
    return token
""",
            file_name="gold_src/function_parameter_scope_hygiene.py",
        )
    )
    builder.add.First(
        astichi.compile(
            """
def first(value):
    scratch = value
    return scratch
""",
            file_name="gold_src/function_parameter_scope_hygiene.py",
        )
    )
    builder.add.Second(
        astichi.compile(
            """
def second(value):
    scratch = value
    return scratch
""",
            file_name="gold_src/function_parameter_scope_hygiene.py",
        )
    )
    builder.add.BodyLocalCollision(
        astichi.compile(
            """
token = "local"
local_token = token
""",
            file_name="gold_src/function_parameter_scope_hygiene.py",
        )
    )
    builder.Root.body.add.First(order=0)
    builder.Root.body.add.Second(order=1)
    builder.Root.inner.add.BodyLocalCollision(order=0)
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    assert "def first(value):" in materialized_source
    assert "def second(value):" in materialized_source
    assert "scratch__astichi_scoped_" not in materialized_source
    assert "value__astichi_scoped_" not in materialized_source
    assert "def owns_param(token):" in materialized_source
    assert "token__astichi_scoped_" in materialized_source
    assert "return token" in materialized_source


if __name__ == "__main__":
    raise SystemExit(
        run_case("function_parameter_scope_hygiene.py", build_case, validate_case)
    )
