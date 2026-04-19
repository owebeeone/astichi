from __future__ import annotations

import ast

from astichi.lowering import (
    DirectiveFuncArgItem,
    DoubleStarFuncArgItem,
    KeywordFuncArgItem,
    PositionalFuncArgItem,
    StarredFuncArgItem,
    extract_funcargs_payload,
)


def _parse_funcargs(source: str) -> ast.Call:
    tree = ast.parse(source)
    stmt = tree.body[0]
    assert isinstance(stmt, ast.Expr)
    assert isinstance(stmt.value, ast.Call)
    return stmt.value


def test_extract_funcargs_payload_preserves_authored_item_order() -> None:
    call = _parse_funcargs(
        """
astichi_funcargs(
    first,
    *more,
    named=value,
    **mapping,
    _=astichi_import(dep),
    _=astichi_export(out),
)
"""
    )

    payload = extract_funcargs_payload(call)

    assert [type(item).__name__ for item in payload.items] == [
        "PositionalFuncArgItem",
        "StarredFuncArgItem",
        "KeywordFuncArgItem",
        "DoubleStarFuncArgItem",
        "DirectiveFuncArgItem",
        "DirectiveFuncArgItem",
    ]

    first, second, third, fourth, fifth, sixth = payload.items
    assert isinstance(first, PositionalFuncArgItem)
    assert isinstance(first.expr, ast.Name)
    assert first.expr.id == "first"

    assert isinstance(second, StarredFuncArgItem)
    assert isinstance(second.expr, ast.Name)
    assert second.expr.id == "more"

    assert isinstance(third, KeywordFuncArgItem)
    assert third.name == "named"
    assert isinstance(third.expr, ast.Name)
    assert third.expr.id == "value"

    assert isinstance(fourth, DoubleStarFuncArgItem)
    assert isinstance(fourth.expr, ast.Name)
    assert fourth.expr.id == "mapping"

    assert isinstance(fifth, DirectiveFuncArgItem)
    assert fifth.directive_name == "astichi_import"
    assert fifth.name == "dep"

    assert isinstance(sixth, DirectiveFuncArgItem)
    assert sixth.directive_name == "astichi_export"
    assert sixth.name == "out"


def test_extract_funcargs_payload_treats_ordinary_underscore_keyword_as_keyword_item() -> None:
    call = _parse_funcargs("astichi_funcargs(_=value)\n")

    payload = extract_funcargs_payload(call)

    assert len(payload.items) == 1
    only = payload.items[0]
    assert isinstance(only, KeywordFuncArgItem)
    assert only.name == "_"
    assert isinstance(only.expr, ast.Name)
    assert only.expr.id == "value"
