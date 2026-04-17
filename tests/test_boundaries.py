"""Tests for the Astichi boundary markers (issue 006 6a + 6b)."""

from __future__ import annotations

import pytest

import astichi
from astichi.lowering import MARKERS_BY_NAME
from astichi.model.ports import IDENTIFIER


def test_import_and_pass_markers_are_registered() -> None:
    # Issue 006 6a: `astichi_import` and `astichi_pass` must be recognised
    # alongside the other call-form markers and self-report as
    # name-bearing identifier declarations.
    assert "astichi_import" in MARKERS_BY_NAME
    assert "astichi_pass" in MARKERS_BY_NAME
    assert MARKERS_BY_NAME["astichi_import"].is_name_bearing() is True
    assert MARKERS_BY_NAME["astichi_pass"].is_name_bearing() is True


def test_compile_recognizes_module_level_boundary_markers() -> None:
    compiled = astichi.compile(
        """
astichi_import(outer_name)
astichi_pass(inner_name)

result = outer_name + inner_name
inner_name = 0
"""
    )

    boundary_markers = [
        marker
        for marker in compiled.markers
        if marker.source_name in ("astichi_import", "astichi_pass")
    ]
    kinds = [(m.source_name, m.name_id) for m in boundary_markers]
    assert kinds == [
        ("astichi_import", "outer_name"),
        ("astichi_pass", "inner_name"),
    ]


def test_compile_emits_identifier_ports_for_boundary_markers() -> None:
    # Issue 006 6a: `astichi_import(name)` surfaces as an IDENTIFIER
    # demand port on the piece, `astichi_pass(name)` as an IDENTIFIER
    # supply port.
    compiled = astichi.compile(
        """
astichi_import(dep)
astichi_pass(result)

result = dep
"""
    )

    dep_port = next(
        port for port in compiled.demand_ports if port.name == "dep"
    )
    assert dep_port.shape is IDENTIFIER
    assert dep_port.placement == "identifier"
    assert "import" in dep_port.sources

    result_port = next(
        port for port in compiled.supply_ports if port.name == "result"
    )
    assert result_port.shape is IDENTIFIER
    assert result_port.placement == "identifier"
    assert "pass" in result_port.sources


def test_placement_accepts_top_prefix_at_module_and_shell_scopes() -> None:
    # Issue 006 6a: the top-of-body prefix in both the module scope and
    # any `@astichi_insert`-decorated shell body is a legal position.
    astichi.compile(
        """
astichi_import(outer)
astichi_pass(top_result)

@astichi_insert(target)
def shell_block():
    astichi_import(shared)
    astichi_pass(nested_out)

    nested_out = shared + 1

top_result = 0
"""
    )


def test_placement_rejects_boundary_after_real_statement_in_module() -> None:
    # Issue 006 6a: boundary markers that appear after any real
    # statement in the module body break the top-prefix rule.
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(\.\.\.\) at line \d+ in module body: "
        r"boundary markers must form the top-of-body prefix",
    ):
        astichi.compile(
            """
x = 1
astichi_import(late)
"""
        )


def test_placement_rejects_boundary_nested_in_if_block() -> None:
    # Issue 006 6a: boundary markers inside a compound statement are
    # not at the top of any Astichi scope body.
    with pytest.raises(
        ValueError,
        match=r"astichi_pass\(\.\.\.\) at line \d+: must appear at the top of",
    ):
        astichi.compile(
            """
if True:
    astichi_pass(stray)
"""
        )


def test_placement_rejects_boundary_inside_non_shell_def() -> None:
    # Issue 006 6a: a plain (non-`@astichi_insert`) def does not open
    # an Astichi scope; markers inside it belong to the surrounding
    # Astichi scope and are therefore misplaced.
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(\.\.\.\) at line \d+: must appear at the top of",
    ):
        astichi.compile(
            """
def helper():
    astichi_import(leaked)
    return leaked
"""
        )


def test_placement_accepts_boundary_as_top_prefix_in_shell_but_rejects_after() -> None:
    # Issue 006 6a: inside a shell body, the prefix rule applies again —
    # markers after a real statement in the shell body are rejected,
    # not leaked through because the module-level prefix accepted them.
    with pytest.raises(
        ValueError,
        match=r"astichi_pass\(\.\.\.\) at line \d+ in shell 'block' body",
    ):
        astichi.compile(
            """
@astichi_insert(target)
def block():
    astichi_import(ok_prefix)
    ok_prefix
    astichi_pass(late_in_shell)
"""
        )


def test_placement_allows_multiple_prefix_boundary_statements() -> None:
    # Issue 006 6a: any number of contiguous import/pass statements at
    # the top of an Astichi scope are legal.
    astichi.compile(
        """
astichi_import(a)
astichi_import(b)
astichi_pass(c)
astichi_pass(d)

c = a
d = b
"""
    )


def test_placement_rejects_boundary_marker_as_decorator_or_nested_call() -> None:
    # Issue 006 6a: boundary calls must be statements; embedded in an
    # expression or as a decorator they are not declarations and are
    # rejected.
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(\.\.\.\) at line \d+",
    ):
        astichi.compile(
            """
result = astichi_import(bad_in_expr)
"""
        )
