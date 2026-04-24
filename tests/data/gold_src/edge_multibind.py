"""Reuse one source instance across multiple edges with edge-local overlays."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def collect(**kwds):
    return kwds


def run(params__astichi_param_hole__):
    values = []
    astichi_hole(body)
    call_result = collect(**astichi_hole(kwargs))
    return (first, second, values, call_result, pinned)


result = run()
""",
            file_name="gold_src/edge_multibind.py",
        )
    )

    builder.add.Params(
        astichi.compile(
            """
def astichi_params(name__astichi_arg__=1):
    pass
""",
            file_name="gold_src/edge_multibind.py",
        )
    )
    builder.add.Body(
        astichi.compile(
            """
values.append(astichi_pass(name, outer_bind=True))
pinned = astichi_pass(name, outer_bind=True)
""",
            file_name="gold_src/edge_multibind.py",
        )
    )
    builder.add.Kw(
        astichi.compile(
            """
astichi_funcargs(key__astichi_arg__=astichi_bind_external(value))
""",
            file_name="gold_src/edge_multibind.py",
        )
    )

    builder.Root.params.add.Params(order=0, arg_names={"name": "first"})
    builder.Root.params.add.Params(order=1, arg_names={"name": "second"})
    builder.Root.body.add.Body(order=0, arg_names={"name": "first"}, keep_names=["pinned"])
    builder.Root.body.add.Body(order=1, arg_names={"name": "second"})
    builder.Root.kwargs.add.Kw(order=0, arg_names={"key": "a"}, bind={"value": 10})
    builder.Root.kwargs.add.Kw(order=1, arg_names={"key": "b"}, bind={"value": 20})
    return builder.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<edge_multibind>")
    assert namespace["result"] == (1, 1, [1, 1], {"a": 10, "b": 20}, 1)
    assert "def run(first=1, second=1):" in materialized_source
    assert "pinned__astichi_scoped_" in materialized_source
    assert "__astichi_arg__" not in materialized_source
    assert "astichi_bind_external" not in materialized_source
    assert "astichi_insert" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("edge_multibind.py", build_case, validate_case))
