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
    __astichi_ph_0__=astichi_import(dep),
    __astichi_ph_1__=astichi_export(out),
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


def test_extract_funcargs_payload_rejects_legacy_underscore_keyword() -> None:
    call = _parse_funcargs("astichi_funcargs(_=value)\n")

    try:
        extract_funcargs_payload(call)
    except ValueError as exc:
        assert "keyword `_` is reserved" in str(exc)
    else:
        raise AssertionError("legacy `_=` funcargs keyword should be rejected")
