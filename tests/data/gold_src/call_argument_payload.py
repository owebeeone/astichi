"""Large funcargs recipe: bind external values plus scoped payload exports."""

from __future__ import annotations

import astichi
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func_combined(head, *args, **kwds):
    return (head, args, kwds)

def func_plain(*args, **kwds):
    return (args, kwds)

def func_star(*args):
    return args

def func_kw(**kwds):
    return kwds

def func_one(head, *args, **kwds):
    return (head, args, kwds)

source_plain_scoped = 100
seed_star_scoped = 200
source_kw_scoped = 300
head_supply = 1
seed_star = 2

result_combined = func_combined(
    astichi_hole(head),
    *astichi_hole(varargs),
    fixed=1,
    **astichi_hole(kwargs),
)
result_plain = func_plain(astichi_hole(plain_args), fixed=2)
result_star = func_star(*astichi_hole(star_only))
result_kw = func_kw(fixed=4, **astichi_hole(kw_only))

result_plain_scoped = func_plain(astichi_hole(plain_args_scoped), fixed=2)
result_star_scoped = func_star(*astichi_hole(star_only_scoped))
result_kw_scoped = func_kw(fixed=4, **astichi_hole(kw_only_scoped))

result_multi_scope = func_one(
    astichi_hole(head_ms),
    *astichi_hole(varargs_ms),
    fixed=1,
    **astichi_hole(kwargs_ms),
)
out_multi_scope = astichi_pass(out_multi_scope)
out_kw_scoped = astichi_pass(out_kw_scoped)
out_star_scoped = astichi_pass(out_star_scoped)
out_plain_scoped = astichi_pass(out_plain_scoped)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )

    builder.add.HeadCombined(
        astichi.compile(
            """
astichi_funcargs("head_slot")
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.add.VarCombined(
        astichi.compile(
            """
astichi_funcargs(2)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.add.SeedDictCombined(
        astichi.compile(
            """
astichi_funcargs(**{"seed": astichi_bind_external(seed)})
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.add.KwNameCombined(
        astichi.compile(
            """
astichi_funcargs(name="x")
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.add.KwFlagCombined(
        astichi.compile(
            """
astichi_funcargs(flag=True)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.Root.head.add.HeadCombined(order=0)
    builder.Root.varargs.add.VarCombined(order=0)
    builder.Root.kwargs.add.SeedDictCombined(order=0)
    builder.Root.kwargs.add.KwNameCombined(order=1)
    builder.Root.kwargs.add.KwFlagCombined(order=2)

    builder.add.Plain(
        astichi.compile(
            """
astichi_funcargs(20)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.Root.plain_args.add.Plain(order=0)

    builder.add.Star(
        astichi.compile(
            """
astichi_funcargs(7)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.Root.star_only.add.Star(order=0)

    builder.add.KwSolo(
        astichi.compile(
            """
astichi_funcargs(msg="solo")
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.Root.kw_only.add.KwSolo(order=0)

    builder.add.PlainScoped(
        astichi.compile(
            """
astichi_funcargs(
    (out := seed),
    _=astichi_import(seed),
    _=astichi_export(out),
)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.Root.plain_args_scoped.add.PlainScoped(order=0)
    builder.assign.PlainScoped.seed.to().Root.source_plain_scoped

    builder.add.StarScoped(
        astichi.compile(
            """
astichi_funcargs(
    (out := astichi_pass(seed)),
    _=astichi_export(out),
)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.Root.star_only_scoped.add.StarScoped(order=0)
    builder.assign.StarScoped.seed.to().Root.seed_star_scoped

    builder.add.KwScoped(
        astichi.compile(
            """
astichi_funcargs(
    msg=(out := seed),
    _=astichi_import(seed),
    _=astichi_export(out),
)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.Root.kw_only_scoped.add.KwScoped(order=0)
    builder.assign.KwScoped.seed.to().Root.source_kw_scoped

    builder.add.HeadMulti(
        astichi.compile(
            """
astichi_funcargs(
    (out := seed),
    _=astichi_import(seed),
    _=astichi_export(out),
)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.add.VarMulti(
        astichi.compile(
            """
astichi_funcargs(
    (out := astichi_pass(seed)),
    _=astichi_export(out),
)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.add.SeedDictMulti(
        astichi.compile(
            """
astichi_funcargs(**{"seed": astichi_bind_external(seed)})
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.add.KwNameMulti(
        astichi.compile(
            """
astichi_funcargs(name="x")
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.add.KwFlagMulti(
        astichi.compile(
            """
astichi_funcargs(flag=True)
""",
            file_name="gold_src/call_argument_payload.py",
        )
    )
    builder.Root.head_ms.add.HeadMulti(order=0)
    builder.Root.varargs_ms.add.VarMulti(order=0)
    builder.Root.kwargs_ms.add.SeedDictMulti(order=0)
    builder.Root.kwargs_ms.add.KwNameMulti(order=1)
    builder.Root.kwargs_ms.add.KwFlagMulti(order=2)
    builder.assign.HeadMulti.seed.to().Root.head_supply
    builder.assign.VarMulti.seed.to().Root.seed_star
    builder.assign.Root.out_multi_scope.to().HeadMulti.out
    builder.assign.Root.out_kw_scoped.to().KwScoped.out
    builder.assign.Root.out_star_scoped.to().StarScoped.out
    builder.assign.Root.out_plain_scoped.to().PlainScoped.out

    return builder.build().bind(seed={"seed": 101})


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<call_argument_payload>")
    assert namespace["result_combined"] == (
        "head_slot",
        (2,),
        {"fixed": 1, "seed": {"seed": 101}, "name": "x", "flag": True},
    )
    assert namespace["result_plain"] == ((20,), {"fixed": 2})
    assert namespace["result_star"] == (7,)
    assert namespace["result_kw"] == {"fixed": 4, "msg": "solo"}
    assert namespace["result_multi_scope"][0] == 1
    assert namespace["result_multi_scope"][1] == (2,)
    assert namespace["out_plain_scoped"] == 100
    assert namespace["out_star_scoped"] == 200
    assert namespace["out_kw_scoped"] == 300
    assert namespace["out_multi_scope"] == 1


if __name__ == "__main__":
    raise SystemExit(run_case("call_argument_payload.py", build_case, validate_case))
