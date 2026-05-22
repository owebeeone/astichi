from __future__ import annotations

import ast

import pytest

import astichi


def test_emit_commented_replaces_only_exact_file_and_line_placeholders() -> None:
    composable = astichi.compile(
        'astichi_comment("{__file__}:{__line__} {field} {__file__}")\n'
        "value = 1\n",
        file_name="src/comments.py",
        line_number=7,
    )

    source = composable.emit_commented()

    assert source == "# src/comments.py:7 {field} src/comments.py\nvalue = 1\n"


def test_materialize_strips_comment_markers_and_preserves_empty_suite() -> None:
    composable = astichi.compile(
        "if enabled:\n"
        '    astichi_comment("nothing to do\\nhere")\n'
    )

    executable = composable.materialize().emit(provenance=False)
    commented = composable.emit_commented()

    assert executable == "if enabled:\n    pass\n"
    assert commented == "if enabled:\n    # nothing to do\n    # here\n    pass\n"


def test_comment_marker_rejects_expression_position() -> None:
    with pytest.raises(ValueError, match="statement-only"):
        astichi.compile('value = astichi_comment("no value")\n')


def test_comment_marker_rejects_non_literal_payload() -> None:
    with pytest.raises(ValueError, match="literal string"):
        astichi.compile('astichi_comment(f"{field}")\n')


def test_comment_marker_rejects_keyword_arguments() -> None:
    with pytest.raises(ValueError, match="keyword arguments"):
        astichi.compile('astichi_comment(text="no kwargs")\n')


def test_emit_commented_does_not_rewrite_string_literals() -> None:
    composable = astichi.compile(
        'text = "astichi_comment(\\"{__file__}:{__line__}\\")"\n'
        'astichi_comment("real {__file__}:{__line__}")\n',
        file_name="src/literals.py",
        line_number=3,
    )

    source = composable.emit_commented()

    assert 'text = \'astichi_comment("{__file__}:{__line__}")\'' in source
    assert "# real src/literals.py:4" in source


def test_emit_commented_comments_before_docstring_are_plain_comments() -> None:
    composable = astichi.compile(
        'astichi_comment("generated")\n'
        '"""Module docs."""\n'
        "from __future__ import annotations\n"
        "value = 1\n"
    )

    source = composable.emit_commented()

    compile(source, "<commented>", "exec")
    assert source.startswith("# generated\n'Module docs.'\n")
    assert ast.get_docstring(ast.parse(source)) == "Module docs."


def test_emit_commented_renders_selected_defaulted_fallback_comments() -> None:
    composable = astichi.compile(
        """
def f():
    with astichi_hole(body) as astichi_fallback:
        astichi_comment("fallback selected")
        return 1
"""
    )

    source = composable.emit_commented()

    assert "with astichi_hole" not in source
    assert "astichi_comment" not in source
    assert "# fallback selected" in source
    assert "return 1" in source


def test_emit_commented_discards_filled_defaulted_fallback_comments() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
def f():
    with astichi_hole(body) as astichi_fallback:
        astichi_comment("fallback only")
        return 1
"""
        )
    )
    builder.add.Payload(astichi.compile("return 2\n"))
    builder.Root.body.add.Payload()

    source = builder.build().emit_commented()

    assert "fallback only" not in source
    assert "astichi_comment" not in source
    assert "return 2" in source
    assert "return 1" not in source
