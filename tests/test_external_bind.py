from __future__ import annotations

import ast

import pytest

import astichi
from astichi.hygiene import analyze_names
from astichi.lowering import apply_external_bindings
from astichi.lowering.markers import recognize_markers
from astichi.model import BasicComposable, extract_demand_ports


def _render_after_bind(source: str, **bindings: object) -> str:
    compiled = astichi.compile(source)
    apply_external_bindings(compiled.tree, bindings)
    return ast.unparse(compiled.tree)


def test_apply_external_bindings_removes_satisfied_marker_and_replaces_loads() -> None:
    rendered = _render_after_bind(
        """
astichi_bind_external(fields)
print(fields)
"""
        ,
        fields=("a", "b"),
    )

    assert rendered == "print(('a', 'b'))"


def test_apply_external_bindings_handles_multiple_names_and_partial_bind() -> None:
    rendered = _render_after_bind(
        """
astichi_bind_external(fields)
astichi_bind_external(row_count)
print(fields)
print(row_count)
"""
        ,
        fields=("a", "b"),
    )

    assert rendered == "astichi_bind_external(row_count)\nprint(('a', 'b'))\nprint(row_count)"


def test_apply_external_bindings_removes_nested_marker_inside_if_body() -> None:
    rendered = _render_after_bind(
        """
astichi_bind_external(outer)
if True:
    astichi_bind_external(inner)
    print(inner)
print(outer)
""",
        outer=1,
        inner=2,
    )

    assert rendered == "if True:\n    print(2)\nprint(1)"


def test_apply_external_bindings_removes_nested_marker_inside_for_body() -> None:
    rendered = _render_after_bind(
        """
for item in range(1):
    astichi_bind_external(inner)
    print(inner)
""",
        inner=2,
    )

    assert rendered == "for item in range(1):\n    print(2)"


def test_apply_external_bindings_respects_function_parameter_shadow() -> None:
    rendered = _render_after_bind(
        """
astichi_bind_external(fields)
print(fields)
def f(fields):
    return fields
"""
        ,
        fields=("a", "b"),
    )

    assert rendered == "print(('a', 'b'))\n\ndef f(fields):\n    return fields"


def test_apply_external_bindings_respects_lambda_parameter_shadow() -> None:
    rendered = _render_after_bind(
        """
astichi_bind_external(fields)
handler = lambda fields: fields
value = fields
"""
        ,
        fields=("a", "b"),
    )

    assert rendered == "handler = lambda fields: fields\nvalue = ('a', 'b')"


def test_apply_external_bindings_respects_comprehension_target_shadow() -> None:
    rendered = _render_after_bind(
        """
astichi_bind_external(fields)
doubled = [fields for fields in range(3)]
value = fields
"""
        ,
        fields=("a", "b"),
    )

    assert rendered == "doubled = [fields for fields in range(3)]\nvalue = ('a', 'b')"


def test_apply_external_bindings_respects_for_target_shadow_and_iter_substitution() -> None:
    rendered = _render_after_bind(
        """
astichi_bind_external(fields)
astichi_bind_external(items)
for fields in items:
    print(fields)
print(items)
"""
        ,
        fields=("outer",),
        items=("x", "y"),
    )

    assert rendered == (
        "for fields in ('x', 'y'):\n"
        "    print(fields)\n"
        "print(('x', 'y'))"
    )


def test_apply_external_bindings_rejects_same_scope_rebind() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(fields)
fields = ()
"""
    )

    with pytest.raises(
        ValueError,
        match=r"same-scope rebind of externally bound name `fields`",
    ):
        apply_external_bindings(compiled.tree, {"fields": ("a", "b")})


def test_apply_external_bindings_rejects_nested_marker_plus_outer_same_scope_rebind() -> None:
    compiled = astichi.compile(
        """
def f():
    if True:
        astichi_bind_external(fields)
    fields = 99
    return fields
"""
    )

    with pytest.raises(
        ValueError,
        match=r"same-scope rebind of externally bound name `fields`",
    ):
        apply_external_bindings(compiled.tree, {"fields": ("a", "b")})


def test_apply_external_bindings_rejects_marker_argument_conflict() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(fields)
astichi_keep(fields)
"""
    )

    with pytest.raises(
        ValueError,
        match=r"external binding `fields` collides with a name-bearing marker identifier .*astichi_keep",
    ):
        apply_external_bindings(compiled.tree, {"fields": ("a", "b")})


def test_apply_external_bindings_round_trips_marker_and_port_recognition() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(fields)
if True:
    astichi_bind_external(row_count)
print(fields)
print(row_count)
"""
    )

    apply_external_bindings(compiled.tree, {"fields": ("a", "b")})
    markers = recognize_markers(compiled.tree)
    provisional = BasicComposable(
        tree=compiled.tree,
        origin=compiled.origin,
        markers=markers,
    )
    classification = analyze_names(provisional, mode="permissive")
    demand_ports = extract_demand_ports(markers, classification)
    bind_external_ports = [
        port for port in demand_ports if port.sources == frozenset({"bind_external"})
    ]

    assert [marker.name_id for marker in markers if marker.source_name == "astichi_bind_external"] == [
        "row_count"
    ]
    assert [port.name for port in bind_external_ports] == ["row_count"]
