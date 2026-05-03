from __future__ import annotations

import ast

from astichi.asttools import (
    AstichiScopeMap,
    has_astichi_insert_decorator,
    import_statement_binding_names,
    is_astichi_insert_call,
    is_astichi_insert_shell,
    is_expression_insert_call,
)


def test_import_statement_binding_names_match_python_local_bindings() -> None:
    tree = ast.parse(
        """
import package.module
import package.module as alias
from pkg import name
from pkg import other as renamed
from pkg import *
"""
    )

    assert isinstance(tree.body[0], ast.Import)
    assert import_statement_binding_names(tree.body[0]) == ("package",)
    assert isinstance(tree.body[1], ast.Import)
    assert import_statement_binding_names(tree.body[1]) == ("alias",)
    assert isinstance(tree.body[2], ast.ImportFrom)
    assert import_statement_binding_names(tree.body[2]) == ("name",)
    assert isinstance(tree.body[3], ast.ImportFrom)
    assert import_statement_binding_names(tree.body[3]) == ("renamed",)
    assert isinstance(tree.body[4], ast.ImportFrom)
    assert import_statement_binding_names(tree.body[4]) == ()
    assert import_statement_binding_names(tree.body[4], include_star=True) == ("*",)


def test_astichi_insert_predicates_cover_insert_surfaces() -> None:
    tree = ast.parse(
        """
@astichi_insert(slot)
def shell():
    pass

value = astichi_insert(expr_slot, payload)
other = astichi_insert(single_arg)
"""
    )
    shell = tree.body[0]
    assert isinstance(shell, ast.FunctionDef)
    expression_assign = tree.body[1]
    other_assign = tree.body[2]
    assert isinstance(expression_assign, ast.Assign)
    assert isinstance(other_assign, ast.Assign)

    assert is_astichi_insert_shell(shell)
    assert has_astichi_insert_decorator(shell.decorator_list)
    assert is_astichi_insert_call(shell.decorator_list[0])
    assert is_expression_insert_call(expression_assign.value)
    assert is_astichi_insert_call(other_assign.value)
    assert not is_expression_insert_call(other_assign.value)


def test_astichi_scope_map_owns_shell_boundary_surfaces() -> None:
    tree = ast.parse(
        """
@decorator(decorator_value)
@astichi_insert(slot)
def shell(arg: ArgAnn = default_value) -> ReturnAnn:
    body_value


@astichi_insert(class_slot)
class Shell(Base, metaclass=Meta):
    class_body_value
"""
    )
    scope_map = AstichiScopeMap.from_tree(tree)
    func = tree.body[0]
    cls = tree.body[1]
    assert isinstance(func, ast.FunctionDef)
    assert isinstance(cls, ast.ClassDef)

    decorator_value = func.decorator_list[0].args[0]
    assert isinstance(decorator_value, ast.Name)
    assert scope_map.scope_for(decorator_value).root is tree
    assert scope_map.scope_for(decorator_value).owns(decorator_value)

    arg = func.args.args[0]
    assert arg.annotation is not None
    assert scope_map.scope_for(arg.annotation).root is func
    assert func.args.defaults
    assert scope_map.scope_for(func.args.defaults[0]).root is func

    assert func.returns is not None
    assert scope_map.scope_for(func.returns).root is tree

    assert scope_map.scope_for(cls.bases[0]).root is tree
    assert scope_map.scope_for(cls.keywords[0].value).root is tree


def test_astichi_scope_map_tracks_expression_insert_payload_scope() -> None:
    tree = ast.parse("value = astichi_insert(slot, payload_name)\n")
    scope_map = AstichiScopeMap.from_tree(tree)
    assign = tree.body[0]
    assert isinstance(assign, ast.Assign)
    call = assign.value
    assert isinstance(call, ast.Call)
    target_arg = call.args[0]
    payload_arg = call.args[1]

    assert scope_map.scope_for(target_arg).root is tree
    assert scope_map.scope_for(payload_arg).root is call


def test_astichi_scope_map_records_nested_python_roots_without_new_scope() -> None:
    tree = ast.parse(
        """
def real_function():
    nested_value = 1
"""
    )
    scope_map = AstichiScopeMap.from_tree(tree)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    assign = func.body[0]
    assert isinstance(assign, ast.Assign)

    assert scope_map.scope_for(assign).root is tree
    assert scope_map.nested_python_root_for(assign) is func
