from __future__ import annotations

import ast

import pytest

import astichi
from astichi.frontend import FrontendComposable


def test_compile_returns_frontend_composable_with_origin_and_line_offsets() -> None:
    compiled = astichi.compile(
        "x = 1\n",
        file_name="original_source.py",
        line_number=10,
        offset=8,
    )

    assert isinstance(compiled, astichi.Composable)
    assert isinstance(compiled, FrontendComposable)
    assert compiled.origin.file_name == "original_source.py"
    assert compiled.origin.line_number == 10
    assert compiled.origin.offset == 8

    stmt = compiled.tree.body[0]
    assert isinstance(compiled.tree, ast.Module)
    assert stmt.lineno == 10
    assert stmt.col_offset == 0


def test_compile_parse_failure_preserves_filename_and_line_number() -> None:
    with pytest.raises(SyntaxError) as exc_info:
        astichi.compile(
            "x =\n",
            file_name="original_source.py",
            line_number=10,
            offset=8,
        )

    assert exc_info.value.filename == "original_source.py"
    assert exc_info.value.lineno == 10
