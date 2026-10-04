"""Bind dormant fallback demands before selecting or replacing the suite."""

from __future__ import annotations

import astichi
from astichi.assembler import AssemblyScope, as_composable, as_external_value, as_identifier
from astichi.model import BasicComposable
from support.golden_case import exec_source, run_case


def build_case() -> astichi.Composable:
    root = astichi.compile(
        """
def fallback(input_value):
    with astichi_hole(body) as astichi_fallback:
        return (astichi_bind_external(label), value__astichi_arg__)

def replaced(input_value):
    with astichi_hole(replaced_body) as astichi_fallback:
        return astichi_bind_external(unused_label)

def nested():
    with astichi_hole(outer_body) as astichi_fallback:
        if True:
            return astichi_bind_external(nested_value)
""",
        file_name="gold_src/defaulted_hole_bindings.py",
    )
    replacement = astichi.compile(
        "return ('replacement', astichi_pass(input_value, outer_bind=True))\n",
        file_name="gold_src/defaulted_hole_bindings.py",
    )
    scope = AssemblyScope(astichi.build())
    scope.add("Root", root)
    scope.wire(as_external_value("fallback"), name="label", build_match=("Root",))
    scope.wire(as_identifier("input_value"), name="value", build_match=("Root",))
    scope.wire(as_external_value(42), name="nested_value", build_match=("Root",))
    scope.wire(
        as_composable(replacement, build_name="Replacement"),
        name="replaced_body",
        build_match=("Root",),
    )
    return scope.build()


def validate_case(
    composable: astichi.Composable,
    materialized: BasicComposable,
    pre_source: str,
    materialized_source: str,
) -> None:
    namespace = exec_source(materialized_source, "<defaulted_hole_bindings>")
    assert namespace["fallback"](7) == ("fallback", 7)
    assert namespace["replaced"](8) == ("replacement", 8)
    assert namespace["nested"]() == 42
    assert "unused_label" not in materialized_source
    assert "__astichi_arg__" not in materialized_source
    assert "astichi_fallback" not in materialized_source


if __name__ == "__main__":
    raise SystemExit(run_case("defaulted_hole_bindings.py", build_case, validate_case))
