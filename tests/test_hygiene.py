from __future__ import annotations

import ast

import pytest

import astichi
from astichi.hygiene import (
    analyze_names,
    assign_scope_identity,
    rename_scope_collisions,
    rewrite_hygienically,
)


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


def test_identifier_suffix_sites_are_local_bindings_and_preserved() -> None:
    # Issue 005 §4 / §9: suffixed class/def names register as normal local
    # bindings (so Load refs resolve locally instead of leaking as implied
    # demands), and the stripped base goes into the preserved set so a
    # post-strip `name_param` / `a_func_name` cannot collide with any
    # competing free binding hygiene sees.
    compiled = astichi.compile(
        """
class name_param__astichi_keep__:
    pass


def a_func_name__astichi_arg__():
    return 1
"""
    )

    classification = analyze_names(compiled, mode="permissive")
    assert "name_param__astichi_keep__" in classification.locals
    assert "a_func_name__astichi_arg__" in classification.locals
    assert "name_param" in classification.preserved
    assert "a_func_name" in classification.preserved


def test_scope_identity_preserves_free_names_but_keeps_local_bindings_internal() -> None:
    compiled = astichi.compile(
        """
print = 1
value = print + outer_name
"""
    )

    analysis = assign_scope_identity(
        compiled,
        preserved_names=frozenset({"print", "outer_name"}),
    )

    print_occurrences = [
        occurrence
        for occurrence in analysis.occurrences
        if occurrence.raw_name == "print"
    ]
    outer_occurrences = [
        occurrence
        for occurrence in analysis.occurrences
        if occurrence.raw_name == "outer_name"
    ]

    assert {occurrence.role for occurrence in print_occurrences} == {"internal"}
    assert {occurrence.scope_id.serial for occurrence in print_occurrences} == {1}
    assert [occurrence.role for occurrence in outer_occurrences] == ["preserved"]
    assert [occurrence.scope_id.serial for occurrence in outer_occurrences] == [1]


def test_fresh_scope_boundaries_give_internal_names_new_scope_but_preserve_outer_names() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(outer_name)
value = 1

@astichi_insert(target_slot)
def inner():
    temp = astichi_keep(value) + outer_name
    return temp
""",
        source_kind="astichi-emitted",
    )
    function_node = compiled.tree.body[2]
    assert isinstance(function_node, ast.FunctionDef)

    analysis = assign_scope_identity(compiled)

    value_occurrences = [
        occurrence
        for occurrence in analysis.occurrences
        if occurrence.raw_name == "value"
    ]
    outer_occurrences = [
        occurrence
        for occurrence in analysis.occurrences
        if occurrence.raw_name == "outer_name"
    ]
    temp_occurrences = [
        occurrence
        for occurrence in analysis.occurrences
        if occurrence.raw_name == "temp"
    ]

    assert [occurrence.scope_id.serial for occurrence in value_occurrences] == [1]
    assert [occurrence.role for occurrence in value_occurrences] == ["internal"]
    assert [occurrence.scope_id.serial for occurrence in outer_occurrences] == [1]
    assert [occurrence.role for occurrence in outer_occurrences] == ["external"]
    assert {occurrence.scope_id.serial for occurrence in temp_occurrences} == {2}
    assert {occurrence.role for occurrence in temp_occurrences} == {"internal"}


def test_plain_python_scope_without_astichi_boundary_is_not_renamed() -> None:
    compiled = astichi.compile(
        """
value = 1

def inner():
    value = 2
    return value

result = value
"""
    )

    analysis = assign_scope_identity(
        compiled,
    )
    rename_scope_collisions(analysis)
    assert ast.unparse(compiled.tree) == (
        "value = 1\n\n"
        "def inner():\n"
        "    value = 2\n"
        "    return value\n"
        "result = value"
    )


def test_scope_collision_renaming_keeps_preserved_spelling_and_renames_other_scopes() -> None:
    compiled = astichi.compile(
        """
value = 1

@astichi_insert(target_slot)
def inner():
    value = 2
    return value

result = astichi_keep(value)
""",
        source_kind="astichi-emitted",
    )
    function_node = compiled.tree.body[1]
    assert isinstance(function_node, ast.FunctionDef)

    analysis = assign_scope_identity(compiled)
    rename_scope_collisions(analysis)
    rendered = ast.unparse(compiled.tree)
    assert "value = 1" in rendered
    assert "value__astichi_scoped_1 = 2" in rendered
    assert "return value__astichi_scoped_1" in rendered
    assert "result = astichi_keep(value)" in rendered


def test_expression_insert_receives_fresh_scope_for_internal_bindings() -> None:
    compiled = astichi.compile(
        """
value = 1
result = astichi_insert(target, (x := 2, x + value))
""",
        source_kind="astichi-emitted",
    )

    analysis = assign_scope_identity(compiled)

    x_occurrences = [
        o for o in analysis.occurrences if o.raw_name == "x"
    ]
    value_occurrences = [
        o for o in analysis.occurrences if o.raw_name == "value"
    ]

    assert len(x_occurrences) == 2
    assert {o.scope_id.serial for o in x_occurrences} == {2}
    assert {o.role for o in x_occurrences} == {"internal"}

    store_values = [o for o in value_occurrences if o.binding_kind == "binding"]
    load_values = [o for o in value_occurrences if o.binding_kind == "reference"]
    assert len(store_values) == 1
    assert store_values[0].scope_id.serial == 1
    assert len(load_values) == 1
    assert load_values[0].scope_id.serial == 2
    assert load_values[0].role == "internal"

def test_expression_insert_free_names_stay_local_to_the_insert_scope() -> None:
    compiled = astichi.compile(
        """
outer = 1
result = astichi_insert(target, outer + 1)
""",
        source_kind="astichi-emitted",
    )

    analysis = assign_scope_identity(compiled)

    outer_occurrences = [
        o for o in analysis.occurrences if o.raw_name == "outer"
    ]
    assert len(outer_occurrences) == 2
    store_outer = [o for o in outer_occurrences if o.binding_kind == "binding"]
    load_outer = [o for o in outer_occurrences if o.binding_kind == "reference"]
    assert store_outer[0].scope_id.serial == 1
    assert load_outer[0].scope_id.serial == 2
    assert load_outer[0].role == "internal"


def test_multiple_expression_inserts_get_distinct_scopes() -> None:
    compiled = astichi.compile(
        """
a = astichi_insert(slot_a, (x := 1, x))
b = astichi_insert(slot_b, (x := 2, x))
""",
        source_kind="astichi-emitted",
    )

    analysis = assign_scope_identity(compiled)

    x_occurrences = [
        o for o in analysis.occurrences if o.raw_name == "x"
    ]
    scopes = {o.scope_id.serial for o in x_occurrences}
    assert len(scopes) == 2


def test_expression_insert_collision_renaming() -> None:
    compiled = astichi.compile(
        """
value = 1
result = astichi_insert(target, (value := 2, value))
outcome = astichi_keep(value)
""",
        source_kind="astichi-emitted",
    )

    analysis = assign_scope_identity(compiled)
    rename_scope_collisions(analysis)
    rendered = ast.unparse(compiled.tree)
    assert "value = 1" in rendered
    assert "outcome = astichi_keep(value)" in rendered
    assert "value__astichi_scoped_" in rendered


def test_scope_collision_renaming_handles_three_scopes_on_same_raw_name() -> None:
    compiled = astichi.compile(
        """
value = 1

@astichi_insert(outer_slot)
def outer():
    value = 2

    @astichi_insert(inner_slot)
    def inner():
        value = 3
        return value

    return value

result = astichi_keep(value)
""",
        source_kind="astichi-emitted",
    )
    outer_function = compiled.tree.body[1]
    assert isinstance(outer_function, ast.FunctionDef)
    inner_function = outer_function.body[1]
    assert isinstance(inner_function, ast.FunctionDef)

    analysis = assign_scope_identity(compiled)
    rename_scope_collisions(analysis)
    rendered = ast.unparse(compiled.tree)
    assert "value = 1" in rendered
    assert "value__astichi_scoped_1 = 2" in rendered
    assert "return value__astichi_scoped_1" in rendered
    assert "value__astichi_scoped_2 = 3" in rendered
    assert "return value__astichi_scoped_2" in rendered
    assert "result = astichi_keep(value)" in rendered
