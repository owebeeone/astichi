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

async def async_run(async_params__astichi_param_hole__):
    return token

def foo(p1__astichi_param_hole__, user_param, p2__astichi_param_hole__):
    user_code(user_param)
    return before, user_param, after

def keyword_only(kw_params__astichi_param_hole__, *, existing=False):
    return existing, inserted

def optional_annotation(optional_params__astichi_param_hole__):
    return timeout
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
    builder.add.P1(
        astichi.compile(
            """
def astichi_params(before):
    pass
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    builder.add.P2(
        astichi.compile(
            """
def astichi_params(after):
    pass
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    builder.add.AsyncParams(
        astichi.compile(
            """
async def astichi_params(token):
    pass
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    builder.add.KeywordOnlyParams(
        astichi.compile(
            """
def astichi_params(*, inserted=True):
    pass
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    builder.add.OptionalAnnotationParams(
        astichi.compile(
            """
def astichi_params(timeout: astichi_hole(timeout_type) = 10):
    pass
""",
            file_name="gold_src/parameter_holes.py",
        )
    )
    builder.Root.params.add.Params(order=0)
    builder.Root.async_params.add.AsyncParams(order=0)
    builder.Root.p1.add.P1(order=0)
    builder.Root.p2.add.P2(order=0)
    builder.Root.kw_params.add.KeywordOnlyParams(order=0)
    builder.Root.optional_params.add.OptionalAnnotationParams(order=0)
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
    assert "async_params__astichi_param_hole__" in pre_source
    assert "p1__astichi_param_hole__" in pre_source
    assert "p2__astichi_param_hole__" in pre_source
    assert "kw_params__astichi_param_hole__" in pre_source
    assert "optional_params__astichi_param_hole__" in pre_source
    assert "def run(session, limit: int=5, *items, debug=False, **options):" in materialized_source
    assert "async def async_run(token):" in materialized_source
    assert "def foo(before, user_param, after):" in materialized_source
    assert "def keyword_only(*, existing=False, inserted=True):" in materialized_source
    assert "def optional_annotation(timeout=10):" in materialized_source
    assert "user_code(user_param)" in materialized_source
    assert "return (before, user_param, after)" in materialized_source
    assert "return (existing, inserted)" in materialized_source
    assert "return timeout" in materialized_source
    assert "value = session" in materialized_source
    assert "session__astichi_scoped_" in materialized_source
    assert "astichi_insert" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("parameter_holes.py", build_case, validate_case))
