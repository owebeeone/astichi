from __future__ import annotations

import ast

import pytest

import astichi


def _exec_emitted(composable) -> dict[str, object]:
    source = composable.emit(provenance=False)
    namespace: dict[str, object] = {}
    exec(compile(source, "<test>", "exec"), namespace)  # noqa: S102
    return namespace


def test_build_funcargs_plain_call_hole_appends_keyword_items_after_authored_keywords() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(astichi_hole(args), fixed=1)\n"))
    builder.add.Impl(astichi.compile("astichi_funcargs(first, named=second, **extra)\n"))
    builder.Root.args.add.Impl()

    materialized = builder.build().materialize()

    rendered = ast.unparse(materialized.tree)
    assert "result = func(first, fixed=1, named=second, **extra)" in rendered


def test_build_funcargs_starred_target_rejects_keyword_items() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(*astichi_hole(args))\n"))
    builder.add.Bad(astichi.compile("astichi_funcargs(named=value)\n"))
    builder.Root.args.add.Bad()

    with pytest.raises(
        ValueError,
        match="starred target args rejects keyword / \\*\\*mapping payload items",
    ):
        builder.build()


def test_build_funcargs_dstar_target_rejects_positional_items() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(**astichi_hole(kwargs))\n"))
    builder.add.Bad(astichi.compile("astichi_funcargs(value)\n"))
    builder.Root.kwargs.add.Bad()

    with pytest.raises(
        ValueError,
        match="double-starred target kwargs rejects positional / starred payload items",
    ):
        builder.build()


def test_build_funcargs_duplicate_explicit_keyword_rejects_at_build() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile("result = func(astichi_hole(args), named=existing)\n")
    )
    builder.add.Bad(astichi.compile("astichi_funcargs(named=value)\n"))
    builder.Root.args.add.Bad()

    with pytest.raises(
        ValueError,
        match="duplicate explicit keyword `named` in call-argument payloads",
    ):
        builder.build()


def test_build_funcargs_import_assign_and_export_survive_materialize() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func(value):
    return value

source_value = 10
result = func(astichi_hole(args))
"""
        )
    )
    builder.add.Impl(
        astichi.compile(
            """
astichi_funcargs(
    (out := seed),
    _=astichi_import(seed),
    _=astichi_export(out),
)
"""
        )
    )
    builder.Root.args.add.Impl()
    builder.assign.Impl.seed.to().Root.source_value

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    assert "astichi_funcargs" not in source
    assert "astichi_insert" not in source
    assert "astichi_import" not in source
    assert "astichi_export" not in source
    assert "result = func((out := source_value))" in source
    assert any(
        port.name == "out" and "export" in port.sources
        for port in materialized.supply_ports
    )

    namespace = _exec_emitted(materialized)
    assert namespace["out"] == 10
    assert namespace["result"] == 10


def test_build_funcargs_compile_arg_names_rewrite_payload_local_import() -> None:
    piece = astichi.compile(
        """
astichi_funcargs(
    (out := seed),
    _=astichi_import(seed),
    _=astichi_export(out),
)
""",
        arg_names={"seed": "source_value"},
    )

    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func(value):
    return value

source_value = 10
result = func(astichi_hole(args))
"""
        )
    )
    builder.add.Impl(piece)
    builder.Root.args.add.Impl()

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    assert "result = func((out := source_value))" in source
    assert any(
        port.name == "out" and "export" in port.sources
        for port in materialized.supply_ports
    )


def test_build_funcargs_unresolved_payload_local_import_remains_demand_port() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func(value):
    return value

result = func(astichi_hole(args))
"""
        )
    )
    builder.add.Impl(
        astichi.compile(
            """
astichi_funcargs(
    (out := seed),
    _=astichi_import(seed),
    _=astichi_export(out),
)
"""
        )
    )
    builder.Root.args.add.Impl()

    materialized = builder.build().materialize()

    assert any(
        port.name == "seed" and "import" in port.sources
        for port in materialized.demand_ports
    )
    assert any(
        port.name == "out" and "export" in port.sources
        for port in materialized.supply_ports
    )


def test_build_funcargs_pass_value_form_emits_argument_and_preserves_export() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func(value):
    return value

seed = 10
result = func(astichi_hole(args))
"""
        )
    )
    builder.add.Impl(
        astichi.compile(
            """
astichi_funcargs(
    (out := astichi_pass(seed)),
    _=astichi_export(out),
)
"""
        )
    )
    builder.Root.args.add.Impl()

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    assert "astichi_pass" not in source
    assert "astichi_export" not in source
    assert "result = func((out := seed))" in source
    assert any(
        port.name == "out" and "export" in port.sources
        for port in materialized.supply_ports
    )

    namespace = _exec_emitted(materialized)
    assert namespace["out"] == 10
    assert namespace["result"] == 10


def test_build_funcargs_assign_disambiguates_same_export_name_across_expression_sources() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func_plain(*args):
    return args

def func_kw(**kwds):
    return kwds

source_plain = 10
source_kw = 20
result_plain = func_plain(astichi_hole(plain_args))
result_kw = func_kw(**astichi_hole(kw_args))
out_plain = astichi_pass(out_plain)
out_kw = astichi_pass(out_kw)
result = (result_plain, result_kw["msg"], out_plain, out_kw)
"""
        )
    )
    builder.add.PlainScoped(
        astichi.compile(
            """
astichi_funcargs(
    (out := seed),
    _=astichi_import(seed),
    _=astichi_export(out),
)
"""
        )
    )
    builder.add.KwScoped(
        astichi.compile(
            """
astichi_funcargs(
    msg=(out := seed),
    _=astichi_import(seed),
    _=astichi_export(out),
)
"""
        )
    )
    builder.Root.plain_args.add.PlainScoped(order=0)
    builder.Root.kw_args.add.KwScoped(order=0)
    builder.assign.PlainScoped.seed.to().Root.source_plain
    builder.assign.KwScoped.seed.to().Root.source_kw
    builder.assign.Root.out_plain.to().PlainScoped.out
    builder.assign.Root.out_kw.to().KwScoped.out

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    assert "__astichi_assign__inst__PlainScoped__name__out" in source
    assert "__astichi_assign__inst__KwScoped__name__out" in source
    assert "out_plain = __astichi_assign__inst__PlainScoped__name__out" in source
    assert "out_kw = __astichi_assign__inst__KwScoped__name__out" in source
    assert "__astichi_assign__inst__PlainScoped__name__out__astichi_scoped_" not in source
    assert "__astichi_assign__inst__KwScoped__name__out__astichi_scoped_" not in source

    namespace = _exec_emitted(materialized)
    assert namespace["result"] == ((10,), 20, 10, 20)


def test_build_funcargs_bind_external_emits_value_argument() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def func(value):
    return value

result = func(astichi_hole(args))
"""
        )
    )
    builder.add.Impl(
        astichi.compile("astichi_funcargs(astichi_bind_external(seed))\n")
    )
    builder.Root.args.add.Impl()

    built = builder.build()
    assert any(
        port.name == "seed" and "bind_external" in port.sources
        for port in built.demand_ports
    )

    materialized = built.bind(seed=10).materialize()
    source = materialized.emit(provenance=False)

    assert "astichi_bind_external" not in source
    assert "result = func(10)" in source
    assert not any(
        port.name == "seed" and "bind_external" in port.sources
        for port in materialized.demand_ports
    )

    namespace = _exec_emitted(materialized)
    assert namespace["result"] == 10


def test_compile_rejects_bind_external_name_collision_with_payload_directive() -> None:
    with pytest.raises(
        ValueError,
        match=(
            r"payload-local astichi_import/export and astichi_bind_external may not "
            r"share the same name `seed` inside astichi_funcargs\(\.\.\.\)"
        ),
    ):
        astichi.compile(
            """
astichi_funcargs(
    astichi_bind_external(seed),
    _=astichi_import(seed),
)
"""
        )
