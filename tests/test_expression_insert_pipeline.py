from __future__ import annotations

import ast

import pytest

import astichi
from astichi.model import BasicComposable


def test_build_scalar_expression_source_replaces_hole() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = astichi_hole(value)\n"))
    builder.add.Impl(astichi.compile("42\n"))
    builder.Root.value.add.Impl()

    result = builder.build().materialize()

    assert isinstance(result, BasicComposable)
    rendered = ast.unparse(result.tree)
    assert "result = 42" in rendered
    assert "astichi_hole" not in rendered


def test_build_scalar_expression_source_rejects_multiple_inserts() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = astichi_hole(value)\n"))
    builder.add.Left(astichi.compile("1\n"))
    builder.add.Right(astichi.compile("2\n"))
    builder.Root.value.add.Left(order=0)
    builder.Root.value.add.Right(order=1)

    with pytest.raises(
        ValueError,
        match="scalar expression target value accepts at most one insert",
    ):
        builder.build()


def test_build_positional_variadic_funcargs_orders_elements() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(*astichi_hole(args))\n"))
    builder.add.First(astichi.compile("astichi_funcargs(first_arg)\n"))
    builder.add.Second(astichi.compile("astichi_funcargs(second_arg)\n"))
    builder.Root.args.add.First(order=20)
    builder.Root.args.add.Second(order=10)

    result = builder.build().materialize()

    rendered = ast.unparse(result.tree)
    assert "result = func(second_arg, first_arg)" in rendered


def test_build_named_variadic_funcargs_uses_edge_order() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(**astichi_hole(kwargs))\n"))
    builder.add.First(astichi.compile("astichi_funcargs(first=one)\n"))
    builder.add.Second(astichi.compile("astichi_funcargs(second=two)\n"))
    builder.Root.kwargs.add.First(order=10)
    builder.Root.kwargs.add.Second(order=20)

    result = builder.build().materialize()

    rendered = ast.unparse(result.tree)
    assert "result = func(first=one, second=two)" in rendered


def test_build_dict_variadic_expression_source_expands_entries() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile("result = {**astichi_hole(entries), fixed: 1}\n")
    )
    builder.add.Impl(astichi.compile("{dynamic_key: computed_value}\n"))
    builder.Root.entries.add.Impl()

    result = builder.build().materialize()

    rendered = ast.unparse(result.tree)
    assert "result = {dynamic_key: computed_value, fixed: 1}" in rendered


def test_build_double_starred_funcargs_rejects_positional_payload() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(**astichi_hole(kwargs))\n"))
    builder.add.Bad(astichi.compile("astichi_funcargs(bad_value)\n"))
    builder.Root.kwargs.add.Bad()

    with pytest.raises(
        ValueError,
        match="double-starred target kwargs rejects positional / starred payload items",
    ):
        builder.build()


def test_build_rejects_legacy_authored_call_argument_insert_surface() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(*astichi_hole(args))\n"))
    builder.add.Legacy(
        astichi.compile(
            "astichi_insert(args, first_arg)\n",
            source_kind="astichi-emitted",
        )
    )
    builder.Root.args.add.Legacy()

    with pytest.raises(
        ValueError,
        match=(
            r"legacy user-authored astichi_insert\(target, expr\) is not "
            r"supported for call-argument targets; use astichi_funcargs\(\.\.\.\)"
        ),
    ):
        builder.build()


def test_build_rejects_expression_insert_for_block_target() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.add.Bad(
        astichi.compile(
            "astichi_insert(body, 42)\n",
            source_kind="astichi-emitted",
        )
    )
    builder.Root.body.add.Bad()

    with pytest.raises(ValueError, match="incompatible port placement"):
        builder.build()


def test_build_rejects_decorator_insert_for_expression_target() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = astichi_hole(value)\n"))
    builder.add.Bad(
        astichi.compile(
            """
@astichi_insert(value)
def provide():
    return 42
""",
            source_kind="astichi-emitted",
        )
    )
    builder.Root.value.add.Bad()

    with pytest.raises(
        ValueError,
        match="cannot satisfy expression target Root.value",
    ):
        builder.build()


def test_materialize_applies_hygiene_to_authored_expression_scope() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
value = 1
result = astichi_hole(slot)
outcome = astichi_keep(value)
"""
        )
    )
    builder.add.Impl(astichi.compile("(value := 2, value)\n"))
    builder.Root.slot.add.Impl()

    materialized = builder.build().materialize()

    rendered = ast.unparse(materialized.tree)
    assert "value = 1" in rendered
    assert "outcome = value" in rendered
    assert "astichi_keep" not in rendered
    assert "value__astichi_scoped_" in rendered


def test_if_condition_expression_insert_walrus_imports_outer_and_exports_binding() -> None:
    """`if astichi_hole(expr):` is an expression site; supply a walrus that uses
    ``(x := astichi_pass(y))`` so the inner ``x`` binding is distinct from the
    pass-through name ``y``, and ``astichi_export(x)`` publishes the bound name.

    Outer ``y`` is wired with ``builder.assign.Impl.y.to().Root.y`` (not
    ``keep_names``). ``build_merge`` synthesizes ``astichi_insert(expr, ...)``
    from the additive edge; contributors do not spell ``astichi_insert`` in
    source.

    The merged module must not mention ``print(x)`` — a second bare ``x`` in
    the root fragment gets a distinct hygiene rename from the walrus ``x`` and
    breaks at runtime. We run ``print(x)`` in the test after ``exec`` (same
    namespace) to verify the walrus binding.
    """
    import io
    from contextlib import redirect_stdout

    root_src = """
y = 10
if astichi_hole(expr):
    pass
"""

    impl_src = """
astichi_export(x)
(x := astichi_pass(y))
"""

    builder = astichi.build()
    builder.add.Root(astichi.compile(root_src))
    builder.add.Impl(astichi.compile(impl_src))
    builder.assign.Impl.y.to().Root.y
    builder.Root.expr.add.Impl()

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    assert "astichi_hole" not in source
    assert "astichi_insert" not in source
    assert "astichi_import" not in source
    assert "astichi_export" not in source
    assert "if (x := y):" in source
    assert "y = 10" in source

    namespace: dict[str, object] = {}
    exec(compile(source, "<test>", "exec"), namespace)

    assert namespace["x"] == 10
    assert namespace["y"] == 10

    buf = io.StringIO()
    with redirect_stdout(buf):
        exec("print(x)", namespace)

    assert buf.getvalue().strip() == "10"


def test_if_condition_expression_insert_walrus_renamed_import_slot_exports_binding() -> None:
    """Expression-site wiring should support a payload-local import name that
    differs from the outer root binding name.

    The walrus still binds and exports ``x``, but the pass-through slot is
    declared as ``y_param`` and explicitly wired onto Root's ``y``.
    """
    root_src = """
y = 10
if astichi_hole(expr):
    pass
"""

    impl_src = """
astichi_export(x)
(x := astichi_pass(y_param))
"""

    builder = astichi.build()
    builder.add.Root(astichi.compile(root_src))
    builder.add.Impl(astichi.compile(impl_src))
    builder.assign.Impl.y_param.to().Root.y
    builder.Root.expr.add.Impl()

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    assert "astichi_hole" not in source
    assert "astichi_insert" not in source
    assert "astichi_import" not in source
    assert "astichi_export" not in source
    assert "y_param" not in source
    assert "if (x := y):" in source

    namespace: dict[str, object] = {}
    exec(compile(source, "<test>", "exec"), namespace)

    assert namespace["x"] == 10
    assert namespace["y"] == 10
