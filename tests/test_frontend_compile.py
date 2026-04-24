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


def test_compile_arg_names_records_identifier_resolutions_eagerly() -> None:
    # `arg_names=` validates keys against IDENTIFIER-shape demand ports
    # and records resolutions in `arg_bindings`. `__astichi_arg__`
    # suffix slots are rewritten eagerly so merge-time validators never
    # see pre-resolution suffix text.
    compiled = astichi.compile(
        """
def wrap(callback__astichi_arg__):
    return callback__astichi_arg__()
""",
        arg_names={"callback": "user_fn"},
    )

    assert dict(compiled.arg_bindings) == {"callback": "user_fn"}
    rendered = ast.unparse(compiled.tree)
    assert "callback__astichi_arg__" not in rendered
    assert "user_fn" in rendered


def test_compile_arg_names_rejects_unknown_slot_name() -> None:
    with pytest.raises(ValueError, match=r"no __astichi_arg__ / astichi_import / astichi_pass slot named `missing`"):
        astichi.compile(
            """
def wrap(callback__astichi_arg__):
    return callback__astichi_arg__()
""",
            arg_names={"missing": "x"},
        )


def test_compile_arg_names_rejects_invalid_identifier_resolution() -> None:
    with pytest.raises(ValueError, match=r"must be a valid Python identifier"):
        astichi.compile(
            """
def wrap(callback__astichi_arg__):
    return callback__astichi_arg__()
""",
            arg_names={"callback": "not an identifier"},
        )


def test_compile_keep_names_preserves_free_identifier_against_rename() -> None:
    # Issue 005 §4 / 5d: `keep_names=` pins identifiers as hygiene
    # preserved without a `__astichi_keep__` suffix in the source.
    compiled = astichi.compile("x = _sentinel\n", keep_names=["_sentinel"])
    assert "_sentinel" in compiled.keep_names

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)
    assert "_sentinel" in rendered


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
