from __future__ import annotations

import ast

import pytest

import astichi
from astichi.hygiene import analyze_names, rewrite_hygienically


def test_analyze_names_classifies_locals_kept_externals_and_unresolved() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(items)
astichi_keep(sys)

value = 1
for loop_item in items:
    total = value + loop_item + missing_name
"""
    )

    classification = analyze_names(compiled, mode="permissive")

    assert classification.locals == frozenset({"value", "loop_item", "total"})
    assert classification.kept == frozenset({"sys"})
    assert classification.externals == frozenset({"items"})
    assert classification.unresolved_free == frozenset({"missing_name"})
    assert [item.name for item in classification.implied_demands] == ["missing_name"]


def test_strict_mode_rejects_unresolved_free_identifiers() -> None:
    compiled = astichi.compile(
        """
value = missing_name
"""
    )

    with pytest.raises(
        ValueError,
        match="unresolved free identifiers in strict mode: missing_name",
    ):
        analyze_names(compiled, mode="strict")


def test_permissive_mode_promotes_unresolved_names_to_implied_demands() -> None:
    compiled = astichi.compile(
        """
value = missing_name
"""
    )

    classification = analyze_names(compiled, mode="permissive")
    assert [item.name for item in classification.implied_demands] == ["missing_name"]


def test_rewrite_hygienically_renames_locals_that_collide_with_preserved_names() -> None:
    compiled = astichi.compile(
        """
print = 1
value = print
"""
    )

    result = rewrite_hygienically(
        compiled,
        mode="permissive",
        preserved_names=frozenset({"print"}),
    )

    assigned_names = [
        node.targets[0].id
        for node in result.tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    ]
    loaded_names = [
        node.value.id
        for node in result.tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name)
    ]

    assert assigned_names[0].startswith("__astichi_local_print_")
    assert loaded_names[0].startswith("__astichi_local_print_")
    assert assigned_names[0] == loaded_names[0]


def test_definitional_name_sites_do_not_become_plain_locals() -> None:
    compiled = astichi.compile(
        """
class name_param__astichi__:
    pass


def a_func_name__astichi__():
    return 1
"""
    )

    classification = analyze_names(compiled, mode="permissive")
    assert "name_param__astichi__" not in classification.locals
    assert "a_func_name__astichi__" not in classification.locals
