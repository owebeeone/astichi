from __future__ import annotations

import ast

import pytest

import astichi
from astichi.model import BasicComposable


def test_materialize_produces_valid_composable() -> None:
    compiled = astichi.compile("value = 1\n")

    result = compiled.materialize()

    assert isinstance(result, BasicComposable)
    assert "value = 1" in ast.unparse(result.tree)


def test_materialize_rejects_unresolved_holes() -> None:
    compiled = astichi.compile("astichi_hole(body)\n")

    with pytest.raises(ValueError, match="mandatory holes remain unresolved: body"):
        compiled.materialize()


def test_materialize_applies_hygiene_closure() -> None:
    compiled = astichi.compile(
        """
value = 1

@astichi_insert(target_slot)
def inner():
    value = 2
    return value

result = astichi_keep(value)
"""
    )

    materialized = compiled.materialize()

    rendered = ast.unparse(materialized.tree)
    assert "value = 1" in rendered
    assert "result = astichi_keep(value)" in rendered
    assert "value__astichi_scoped_" in rendered


def test_materialize_allows_implied_demands() -> None:
    compiled = astichi.compile("value = missing_name\n")

    result = compiled.materialize()

    assert isinstance(result, BasicComposable)
    assert "missing_name" in ast.unparse(result.tree)


def test_end_to_end_additive_composition() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
astichi_hole(init)
astichi_hole(body)
astichi_export(result)
"""
        )
    )
    builder.add.Setup(astichi.compile("total = 0\n"))
    builder.add.Step1(astichi.compile("total = total + 1\n"))
    builder.add.Step2(astichi.compile("total = total + 2\n"))
    builder.Root.init.add.Setup()
    builder.Root.body.add.Step1(order=0)
    builder.Root.body.add.Step2(order=1)

    built = builder.build()
    materialized = built.materialize()

    rendered = ast.unparse(materialized.tree)
    assert "total = 0" in rendered
    assert "total = total + 1" in rendered
    assert "total = total + 2" in rendered
    assert rendered.index("total = 0") < rendered.index("total = total + 1")
    assert rendered.index("total = total + 1") < rendered.index("total = total + 2")
