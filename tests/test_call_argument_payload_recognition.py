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
    _=astichi_import(source),
    _=astichi_export(result),
)
"""
    )

    demand_names = {port.name for port in compiled.demand_ports}
    supply_names = {port.name for port in compiled.supply_ports}
    marker_names = {marker.source_name for marker in compiled.markers}

    assert "source" in demand_names
    assert "result" in supply_names
    assert "astichi_funcargs" in marker_names


def test_direct_funcargs_directive_calls_preserve_authored_order() -> None:
    tree = ast.parse(
        """
astichi_funcargs(
    _=astichi_export(out),
    _=astichi_import(dep),
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
        match="only top-level expression statement in a call-argument payload snippet",
    ):
        astichi.compile(source)


def test_compile_rejects_astichi_pass_in_special_carrier() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_pass\(\.\.\.\) is not valid in _=",
    ):
        astichi.compile("astichi_funcargs(_=astichi_pass(total))\n")


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
        match=r"astichi_import\(\.\.\.\) / astichi_export\(\.\.\.\) are only valid as direct _= carriers",
    ):
        astichi.compile(source)


def test_compile_rejects_wrapped_special_carrier_forms() -> None:
    with pytest.raises(
        ValueError,
        match="wrapped forms are not supported",
    ):
        astichi.compile(
            "astichi_funcargs(_=(astichi_import(source), astichi_export(result)))\n"
        )


def test_compile_allows_ordinary_underscore_keyword_argument() -> None:
    compiled = astichi.compile("astichi_funcargs(_=value)\n")

    assert {port.name for port in compiled.demand_ports} == {"value"}
    assert {port.name for port in compiled.supply_ports} == set()
