from __future__ import annotations

import ast

import pytest

import astichi
from astichi.model import BasicComposable


def test_build_scalar_expression_insert_replaces_hole() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = astichi_hole(value)\n"))
    builder.add.Impl(astichi.compile("astichi_insert(value, 42)\n"))
    builder.Root.value.add.Impl()

    result = builder.build().materialize()

    assert isinstance(result, BasicComposable)
    rendered = ast.unparse(result.tree)
    assert "result = 42" in rendered
    assert "astichi_hole" not in rendered


def test_build_scalar_expression_insert_rejects_multiple_inserts() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = astichi_hole(value)\n"))
    builder.add.Left(astichi.compile("astichi_insert(value, 1)\n"))
    builder.add.Right(astichi.compile("astichi_insert(value, 2)\n"))
    builder.Root.value.add.Left(order=0)
    builder.Root.value.add.Right(order=1)

    with pytest.raises(
        ValueError,
        match="scalar expression target value accepts at most one insert",
    ):
        builder.build()


def test_build_positional_variadic_expression_insert_orders_elements() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(*astichi_hole(args))\n"))
    builder.add.First(astichi.compile("astichi_insert(args, first_arg)\n"))
    builder.add.Second(astichi.compile("astichi_insert(args, second_arg)\n"))
    builder.Root.args.add.First(order=20)
    builder.Root.args.add.Second(order=10)

    result = builder.build().materialize()

    rendered = ast.unparse(result.tree)
    assert "result = func(second_arg, first_arg)" in rendered


def test_build_named_variadic_expression_insert_uses_inline_order() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(**astichi_hole(kwargs))\n"))
    builder.add.Impl(
        astichi.compile(
            """
astichi_insert(kwargs, {first: one})
astichi_insert(kwargs, {second: two}, order=20)
"""
        )
    )
    builder.Root.kwargs.add.Impl()

    result = builder.build().materialize()

    rendered = ast.unparse(result.tree)
    assert "result = func(first=one, second=two)" in rendered


def test_build_dict_variadic_expression_insert_expands_entries() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile("result = {**astichi_hole(entries), fixed: 1}\n")
    )
    builder.add.Impl(
        astichi.compile("astichi_insert(entries, {dynamic_key: computed_value})\n")
    )
    builder.Root.entries.add.Impl()

    result = builder.build().materialize()

    rendered = ast.unparse(result.tree)
    assert "result = {dynamic_key: computed_value, fixed: 1}" in rendered


def test_build_named_variadic_expression_insert_rejects_non_dict_payload() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = func(**astichi_hole(kwargs))\n"))
    builder.add.Bad(astichi.compile("astichi_insert(kwargs, bad_value)\n"))
    builder.Root.kwargs.add.Bad()

    with pytest.raises(
        ValueError,
        match="named variadic target kwargs requires dict-display expression inserts",
    ):
        builder.build()


def test_build_rejects_expression_insert_for_block_target() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.add.Bad(astichi.compile("astichi_insert(body, 42)\n"))
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
"""
        )
    )
    builder.Root.value.add.Bad()

    with pytest.raises(
        ValueError,
        match="cannot satisfy expression target Root.value",
    ):
        builder.build()


def test_materialize_applies_hygiene_to_inserted_expression_scope() -> None:
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
    builder.add.Impl(astichi.compile("astichi_insert(slot, (value := 2, value))\n"))
    builder.Root.slot.add.Impl()

    materialized = builder.build().materialize()

    rendered = ast.unparse(materialized.tree)
    assert "value = 1" in rendered
    assert "outcome = value" in rendered
    assert "astichi_keep" not in rendered
    assert "value__astichi_scoped_" in rendered
