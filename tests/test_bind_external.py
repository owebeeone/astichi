from __future__ import annotations

import ast

import pytest

import astichi
from astichi.model import BasicComposable


def _bind_external_demand_names(composable: BasicComposable) -> list[str]:
    return sorted(
        port.name
        for port in composable.demand_ports
        if port.sources == frozenset({"bind_external"})
    )


def test_bind_external_keyword_form_returns_new_composable() -> None:
    snippet = astichi.compile(
        """
astichi_bind_external(fields)
print(fields)
"""
    )

    bound = snippet.bind(fields=("a", "b"))

    assert isinstance(bound, BasicComposable)
    assert bound is not snippet
    assert ast.unparse(bound.tree) == "print(('a', 'b'))"
    assert ast.unparse(snippet.tree) == "astichi_bind_external(fields)\nprint(fields)"
    assert _bind_external_demand_names(bound) == []


def test_bind_external_mapping_form_is_supported() -> None:
    snippet = astichi.compile(
        """
astichi_bind_external(fields)
print(fields)
"""
    )

    bound = snippet.bind({"fields": ("x", "y")})

    assert ast.unparse(bound.tree) == "print(('x', 'y'))"


def test_bind_external_kwargs_win_over_mapping_on_collision() -> None:
    snippet = astichi.compile(
        """
astichi_bind_external(fields)
print(fields)
"""
    )

    bound = snippet.bind({"fields": ("x", "y")}, fields=("a", "b"))

    assert ast.unparse(bound.tree) == "print(('a', 'b'))"


def test_bind_external_rejects_non_identifier_mapping_key() -> None:
    snippet = astichi.compile("astichi_bind_external(fields)\n")

    with pytest.raises(
        ValueError,
        match=r"binding key `1fields` is not a valid Python identifier",
    ):
        snippet.bind({"1fields": ("a",)})


def test_bind_external_rejects_unknown_key() -> None:
    snippet = astichi.compile("astichi_bind_external(fields)\n")

    with pytest.raises(
        ValueError,
        match=r"no astichi_bind_external\(feilds\) site found; known bind-external demands on this composable: \('fields',\)",
    ):
        snippet.bind(feilds=("a", "b"))


def test_bind_external_rejects_rebind_of_already_applied_name() -> None:
    snippet = astichi.compile("astichi_bind_external(fields)\nprint(fields)\n")
    bound = snippet.bind(fields=("a", "b"))

    with pytest.raises(
        ValueError,
        match=r"cannot re-bind `fields`: the external binding has already been applied to this composable",
    ):
        bound.bind(fields=("x", "y"))


def test_bind_external_allows_partial_bind_across_two_calls() -> None:
    snippet = astichi.compile(
        """
astichi_bind_external(fields)
astichi_bind_external(row_count)
print(fields)
print(row_count)
"""
    )

    stage1 = snippet.bind(fields=("a", "b"))
    stage2 = stage1.bind(row_count=2)

    assert _bind_external_demand_names(stage1) == ["row_count"]
    assert _bind_external_demand_names(stage2) == []
    assert ast.unparse(stage2.tree) == "print(('a', 'b'))\nprint(2)"


def test_bind_external_empty_bind_is_no_op_snapshot() -> None:
    snippet = astichi.compile("x = 1\nprint(x)\n")

    same = snippet.bind()

    assert isinstance(same, BasicComposable)
    assert same is not snippet
    assert ast.unparse(same.tree) == ast.unparse(snippet.tree)
    assert _bind_external_demand_names(same) == []
