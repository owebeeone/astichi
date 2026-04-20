"""AST source-location (provenance) invariants for synthesized nodes."""

from __future__ import annotations

import ast

import pytest

from astichi import compile as astichi_compile
from astichi.ast_provenance import (
    assert_tree_has_ast_source_locations,
    has_valid_ast_source_location,
    iter_nodes_missing_ast_source_location,
    propagate_ast_source_locations,
    requires_ast_source_location,
)
from astichi.lowering.unroll import unroll_tree
from astichi.shell_refs import ref_path_to_ast


def test_requires_ast_source_location_excludes_module() -> None:
    tree = ast.parse("x = 1")
    assert not requires_ast_source_location(tree)
    assert requires_ast_source_location(tree.body[0])


def test_propagate_from_donor_fills_synthetic_expr() -> None:
    donor = ast.parse("f()").body[0].value
    assert isinstance(donor, ast.Call)
    fresh = ast.Call(
        func=ast.Name(id="g", ctx=ast.Load()),
        args=[],
        keywords=[],
    )
    assert not has_valid_ast_source_location(fresh)
    propagate_ast_source_locations(fresh, donor)
    assert has_valid_ast_source_location(fresh)
    for node in ast.walk(fresh):
        if requires_ast_source_location(node):
            assert has_valid_ast_source_location(node), type(node).__name__


def test_ref_path_to_ast_inherits_from_donor() -> None:
    donor = ast.parse("Foo.Bar[0]").body[0].value
    assert isinstance(donor, ast.expr)
    path = ("X", "Y", 1)
    expr = ref_path_to_ast(path, location_donor=donor)
    assert expr.lineno == donor.lineno
    assert not list(iter_nodes_missing_ast_source_location(expr))


def test_compile_snippet_tree_has_locations() -> None:
    composable = astichi_compile(
        "astichi_bind_external(T)\n"
        "for i in astichi_for((1, 2)):\n"
        "    astichi_hole(slot)\n"
    )
    assert_tree_has_ast_source_locations(composable.tree)


def test_unroll_tree_preserves_locations() -> None:
    tree = astichi_compile(
        "for i in astichi_for((1,)):\n"
        "    astichi_hole(h)\n"
    ).tree
    out = unroll_tree(tree)
    assert_tree_has_ast_source_locations(out)


def test_build_merge_materialized_tree_has_locations() -> None:
    from astichi import build

    a = astichi_compile("astichi_hole(slot)\n")
    b = astichi_compile("y = 1\n")
    g = build()
    g.add.A(a)
    g.add.B(b)
    g.A.slot.add.B()
    merged = g.build().materialize()
    assert_tree_has_ast_source_locations(merged.tree)


def test_build_merge_unrolled_has_locations() -> None:
    from astichi import build

    a = astichi_compile(
        "for x in astichi_for((1, 2)):\n"
        "    astichi_hole(slot)\n"
    )
    b0 = astichi_compile("a = 1\n")
    b1 = astichi_compile("b = 2\n")
    g = build()
    g.add.A(a)
    g.add.B0(b0)
    g.add.B1(b1)
    g.A.slot[0].add.B0()
    g.A.slot[1].add.B1()
    merged = g.build(unroll=True).materialize()
    assert_tree_has_ast_source_locations(merged.tree)


def test_synthetic_expr_without_propagate_fails_invariant() -> None:
    orphan = ast.Expr(
        value=ast.Call(
            func=ast.Name(id="f", ctx=ast.Load()),
            args=[],
            keywords=[],
        )
    )
    with pytest.raises(AssertionError, match="lack source location"):
        assert_tree_has_ast_source_locations(
            ast.Module(body=[orphan], type_ignores=[])
        )
