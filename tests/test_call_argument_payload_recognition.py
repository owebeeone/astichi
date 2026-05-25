from __future__ import annotations

import ast

import pytest

import astichi
from astichi.lowering import direct_funcargs_directive_calls


def test_compile_accepts_top_level_astichi_funcargs_payload() -> None:
    compiled = astichi.compile(
        """
astichi_funcargs(
    1,
    __astichi_ph_0__=astichi_import(source),
    __astichi_ph_1__=astichi_export(result),
)
"""
    )

    demand_names = {port.name for port in compiled.demand_ports}
    supply_names = {port.name for port in compiled.supply_ports}
    marker_names = {marker.source_name for marker in compiled.markers}

    assert "source" in demand_names
    assert "result" in supply_names
    assert "astichi_funcargs" in marker_names


def test_compile_accepts_boundary_prefix_before_astichi_funcargs_payload() -> None:
    compiled = astichi.compile(
        """
astichi_pyimport(module=foo, names=(bar,))
astichi_keep(foo)
astichi_funcargs(name__astichi_arg__, key=b)
"""
    )

    assert [production.name for production in compiled.describe().productions] == [
        "__funcargs__"
    ]
    assert {port.name for port in compiled.demand_ports} == {"name", "b"}


def test_direct_funcargs_directive_calls_preserve_authored_order() -> None:
    tree = ast.parse(
        """
astichi_funcargs(
    __astichi_ph_0__=astichi_export(out),
    __astichi_ph_1__=astichi_import(dep),
)
"""
    )
    call = tree.body[0].value
    assert isinstance(call, ast.Call)

    directives = direct_funcargs_directive_calls(call)
    assert [directive.func.id for directive in directives] == [
        "astichi_export",
        "astichi_import",
    ]


@pytest.mark.parametrize(
    "source",
    [
        "value = astichi_funcargs(1)\n",
        "astichi_funcargs(1)\nastichi_funcargs(2)\n",
        "def outer():\n    astichi_funcargs(1)\n",
    ],
)
def test_compile_rejects_non_payload_placement(source: str) -> None:
    with pytest.raises(
        ValueError,
        match="only non-prefix top-level expression statement in a call-argument payload snippet",
    ):
        astichi.compile(source)


def test_compile_rejects_astichi_pass_in_directive_placeholder() -> None:
    with pytest.raises(
        ValueError,
        match="directive placeholders may only carry direct astichi_import",
    ):
        astichi.compile("astichi_funcargs(__astichi_ph_0__=astichi_pass(total))\n")


def test_compile_rejects_sentinel_wrapped_astichi_pass_in_directive_placeholder() -> None:
    with pytest.raises(
        ValueError,
        match="directive placeholders may only carry direct astichi_import",
    ):
        astichi.compile("astichi_funcargs(__astichi_ph_0__=astichi_pass(total)._)\n")


@pytest.mark.parametrize(
    "source",
    [
        "astichi_funcargs(astichi_import(source))\n",
        "astichi_funcargs(result=astichi_export(value))\n",
    ],
)
def test_compile_rejects_import_export_outside_direct_special_carrier(
    source: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(\.\.\.\) / astichi_export\(\.\.\.\) are only valid as direct __astichi_ph_\{N\}__= carriers",
    ):
        astichi.compile(source)


def test_compile_rejects_wrapped_special_carrier_forms() -> None:
    with pytest.raises(
        ValueError,
        match="directive placeholders may only carry direct astichi_import",
    ):
        astichi.compile(
            "astichi_funcargs(__astichi_ph_0__=(astichi_import(source), astichi_export(result)))\n"
        )


def test_compile_rejects_legacy_underscore_keyword_carrier() -> None:
    with pytest.raises(ValueError, match="keyword `_` is reserved"):
        astichi.compile("astichi_funcargs(_=value)\n")


@pytest.mark.parametrize(
    ("source", "match"),
    [
        (
            "astichi_funcargs(__astichi_ph_0__=astichi_import())\n",
            r"astichi_import expects 1 positional arguments",
        ),
        (
            "astichi_funcargs(__astichi_ph_0__=astichi_export(source.attr))\n",
            r"astichi_export requires a bare identifier-like first argument",
        ),
        (
            "astichi_funcargs(astichi_bind_external())\n",
            r"astichi_bind_external expects 1 positional arguments",
        ),
        (
            "astichi_funcargs(astichi_bind_external(source.attr))\n",
            r"astichi_bind_external requires a bare identifier-like first argument",
        ),
    ],
)
def test_compile_rejects_malformed_payload_marker_shapes(
    source: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        astichi.compile(source)


@pytest.mark.parametrize(
    "source",
    [
        "astichi_funcargs(__astichi_ph_1__=astichi_import(source))\n",
        (
            "astichi_funcargs("
            "__astichi_ph_0__=astichi_import(source), "
            "__astichi_ph_2__=astichi_export(out)"
            ")\n"
        ),
    ],
)
def test_compile_rejects_non_contiguous_directive_placeholders(source: str) -> None:
    with pytest.raises(ValueError, match="contiguous and ordered"):
        astichi.compile(source)
