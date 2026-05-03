"""Tests for `astichi_ref(...)` per dev-docs/historical/AstichiV3ExternalRefBind.m4.

Covers the full lowered surface:

- §1 core: positional value, `external=name` sugar
- §2 accepted values: literal strings, f-strings, compile-time
  subscript over loop-var / externally-bound containers
- §3 lowering: bare names, dotted attributes
- §3a sentinel wrapper: Store / AugStore / Del context propagation,
  transparent single-strip continuation in postfix syntax
- §7 examples (loop + read-and-write)
- §8 rejection cases
"""

from __future__ import annotations

import ast

import pytest

import astichi
from astichi.lowering import (
    evaluate_restricted_path_expression,
    extract_dotted_reference_chain,
)


def _materialized(source: str, **bindings: object) -> str:
    compiled = astichi.compile(source)
    if bindings:
        compiled = compiled.bind(**bindings)
    return ast.unparse(compiled.materialize().tree)


def test_reference_path_helpers_evaluate_without_lowering() -> None:
    expr = ast.parse("f'{prefix}.field'", mode="eval").body
    assert isinstance(expr, ast.JoinedStr)
    expr.values[0] = ast.Constant(value="self")

    assert evaluate_restricted_path_expression(expr) == ("self", "field")


def test_extract_dotted_reference_chain_without_rewriting() -> None:
    expr = ast.parse("pkg.mod.attr", mode="eval").body

    assert extract_dotted_reference_chain(expr) == ("pkg", "mod", "attr")


def test_extract_dotted_reference_chain_rejects_non_chain() -> None:
    expr = ast.parse("pkg[0]", mode="eval").body

    with pytest.raises(ValueError, match="dotted Name/Attribute"):
        extract_dotted_reference_chain(expr)


# ---------------------------------------------------------------------------
# §1 / §3 core: positional value + dotted lowering
# ---------------------------------------------------------------------------


def test_ref_lowers_bare_name_literal() -> None:
    rendered = _materialized("value = astichi_ref('foo')\n")
    assert rendered.strip() == "value = foo"


def test_ref_lowers_dotted_attribute_chain_literal() -> None:
    rendered = _materialized("value = astichi_ref('pkg.mod.attr')\n")
    assert rendered.strip() == "value = pkg.mod.attr"


def test_ref_lowers_inside_call_argument_position() -> None:
    rendered = _materialized("call(astichi_ref('a.b'))\n")
    assert rendered.strip() == "call(a.b)"


# ---------------------------------------------------------------------------
# §1 sugar: external=name desugars + flows through bind()
# ---------------------------------------------------------------------------


def test_ref_external_kwarg_lowers_after_bind() -> None:
    rendered = _materialized(
        "value = astichi_ref(external=path)\n",
        path="pkg.mod.attr",
    )
    assert rendered.strip() == "value = pkg.mod.attr"


def test_ref_external_kwarg_surfaces_bind_external_demand_port() -> None:
    compiled = astichi.compile("value = astichi_ref(external=path)\n")
    demands = {p.name for p in compiled.demand_ports}
    assert "path" in demands


def test_ref_with_inner_bind_external_lowers_after_bind() -> None:
    rendered = _materialized(
        "value = astichi_ref(astichi_bind_external(path))\n",
        path="self.attr",
    )
    assert rendered.strip() == "value = self.attr"


def test_ref_external_kwarg_unbound_is_rejected_by_materialize_gate() -> None:
    compiled = astichi.compile("value = astichi_ref(external=path)\n")
    with pytest.raises(ValueError, match="external binding for `path`"):
        compiled.materialize()


# ---------------------------------------------------------------------------
# §2 f-string with externally bound substring
# ---------------------------------------------------------------------------


def test_ref_fstring_with_bound_external_string_lowers() -> None:
    rendered = _materialized(
        """
astichi_bind_external(prefix)
value = astichi_ref(f'{prefix}.field')
""",
        prefix="self",
    )
    assert "value = self.field" in rendered


def test_ref_fstring_concatenates_two_bound_externals() -> None:
    rendered = _materialized(
        """
astichi_bind_external(a)
astichi_bind_external(b)
value = astichi_ref(f'{a}.{b}')
""",
        a="self",
        b="counter",
    )
    assert "value = self.counter" in rendered


# ---------------------------------------------------------------------------
# §2 compile-time subscript over a bound external container
# ---------------------------------------------------------------------------


def test_ref_fstring_subscript_into_bound_tuple() -> None:
    rendered = _materialized(
        """
astichi_bind_external(names)
value = astichi_ref(f'{names[0]}.{names[1]}')
""",
        names=("self", "f0"),
    )
    assert "value = self.f0" in rendered


# ---------------------------------------------------------------------------
# §2 + unroll loop variable becomes literal then folds into the path
# ---------------------------------------------------------------------------


def test_ref_inside_unrolled_for_uses_loop_var_index() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            """
for i in astichi_for((0, 1, 2)):
    value = astichi_ref(f'self.f{i}')
""",
        )
    )
    merged = builder.build(unroll=True)
    rendered = ast.unparse(merged.materialize().tree)
    assert "value = self.f0" in rendered
    assert "value = self.f1" in rendered
    assert "value = self.f2" in rendered
    assert "astichi_ref" not in rendered
    assert "astichi_for" not in rendered


# ---------------------------------------------------------------------------
# §3a sentinel wrapper: Store / AugStore / Del
# ---------------------------------------------------------------------------


def test_ref_sentinel_assign_propagates_store_ctx() -> None:
    rendered = _materialized(
        "astichi_ref('self.f0').astichi_v = 42\n",
    )
    assert rendered.strip() == "self.f0 = 42"


def test_ref_sentinel_underscore_shorthand_assign() -> None:
    rendered = _materialized(
        "astichi_ref('self.f0')._ = 42\n",
    )
    assert rendered.strip() == "self.f0 = 42"


def test_ref_sentinel_augassign_propagates_store_ctx() -> None:
    rendered = _materialized(
        "astichi_ref('self.f0').astichi_v += 1\n",
    )
    assert rendered.strip() == "self.f0 += 1"


def test_ref_sentinel_del_propagates_del_ctx() -> None:
    rendered = _materialized(
        "del astichi_ref('self.f0').astichi_v\n",
    )
    assert rendered.strip() == "del self.f0"


def test_ref_sentinel_with_external_bind_for_rhs() -> None:
    # End-to-end: bind two externals, one writes a path, one reads.
    rendered = _materialized(
        """
astichi_ref(external=path).astichi_v = 42
total = astichi_ref(external=path)
""",
        path="self.counter",
    )
    assert "self.counter = 42" in rendered
    assert "total = self.counter" in rendered


def test_ref_sentinel_inside_unrolled_loop_round_trips_paths() -> None:
    builder = astichi.build()
    builder.add.A(
        astichi.compile(
            """
for spec in astichi_for(((1, 'self.f0', 42), (2, 'self.f1', 43))):
    if not (m & spec[0]):
        astichi_ref(spec[1]).astichi_v = spec[2]
        m |= spec[0]
"""
        )
    )
    merged = builder.build(unroll=True)
    rendered = ast.unparse(merged.materialize().tree)
    # `astichi_ref(spec[1]).astichi_v = ...` lowers per iteration; only
    # the LHS path is materialised (the RHS `spec[2]` is left intact as
    # an ordinary subscript expression in the emitted source).
    assert "self.f0 = " in rendered
    assert "self.f1 = " in rendered
    assert "astichi_ref" not in rendered
    assert "astichi_for" not in rendered


# ---------------------------------------------------------------------------
# §3a constraint: any other attr name is preserved literally
# ---------------------------------------------------------------------------


def test_ref_non_sentinel_attribute_extends_lowered_path() -> None:
    rendered = _materialized("value = astichi_ref('pkg.mod').other\n")
    assert rendered.strip() == "value = pkg.mod.other"


def test_ref_chained_calls_compose_reference_path_segments() -> None:
    rendered = _materialized(
        "value = astichi_ref('cls_ctx').astichi_ref('class_name')\n"
    )
    assert rendered.strip() == "value = cls_ctx.class_name"


def test_ref_method_form_extends_arbitrary_base_expression() -> None:
    rendered = _materialized(
        "self.astichi_ref(external=field_name)._ = 1\n",
        field_name="label",
    )
    assert rendered.strip() == "self.label = 1"


def test_ref_method_form_external_kwarg_surfaces_bind_external_demand_port() -> None:
    compiled = astichi.compile("value = self.astichi_ref(external=field_name)\n")
    demands = {p.name for p in compiled.demand_ports}
    assert "field_name" in demands


# ---------------------------------------------------------------------------
# §3a transparent sentinel continuation
# ---------------------------------------------------------------------------


def test_ref_sentinel_attribute_chain_is_transparent_once() -> None:
    rendered = _materialized("value = astichi_ref('pkg.mod')._.other\n")
    assert rendered.strip() == "value = pkg.mod.other"


def test_ref_sentinel_call_is_transparent_once() -> None:
    rendered = _materialized("value = astichi_ref('factory').astichi_v()\n")
    assert rendered.strip() == "value = factory()"


def test_ref_sentinel_store_chain_is_transparent_once() -> None:
    rendered = _materialized("astichi_ref('self.f0')._.value = 1\n")
    assert rendered.strip() == "self.f0.value = 1"


def test_ref_sentinel_strips_once_so_real_underscore_field_remains() -> None:
    rendered = _materialized("value = astichi_ref('obj')._._\n")
    assert rendered.strip() == "value = obj._"


def test_reject_bare_ref_statement() -> None:
    with pytest.raises(ValueError, match=r"astichi_ref\(\.\.\.\) at line \d+ is value-form only"):
        astichi.compile("astichi_ref('pkg.mod')\n")


def test_reject_bare_ref_sentinel_statement() -> None:
    with pytest.raises(ValueError, match=r"astichi_ref\(\.\.\.\) at line \d+ is value-form only"):
        astichi.compile("astichi_ref('pkg.mod').astichi_v\n")


# ---------------------------------------------------------------------------
# §8 rejection cases — value-form
# ---------------------------------------------------------------------------


def test_reject_ref_zero_args() -> None:
    with pytest.raises(ValueError, match="astichi_ref"):
        astichi.compile("value = astichi_ref()\n")


def test_reject_ref_external_with_extra_kwarg() -> None:
    with pytest.raises(ValueError, match="astichi_ref"):
        astichi.compile("value = astichi_ref(external=path, other=x)\n")


def test_reject_ref_external_with_string_literal_value() -> None:
    with pytest.raises(ValueError, match="bare identifier"):
        astichi.compile('value = astichi_ref(external="pkg.mod")\n')


def test_reject_ref_double_dot_path() -> None:
    compiled = astichi.compile("value = astichi_ref('a..b')\n")
    with pytest.raises(ValueError, match="empty segment"):
        compiled.materialize()


def test_reject_ref_empty_string_path() -> None:
    compiled = astichi.compile("value = astichi_ref('')\n")
    with pytest.raises(ValueError, match="must not be empty"):
        compiled.materialize()


def test_reject_ref_fstring_with_attribute_lookup_part() -> None:
    compiled = astichi.compile("value = astichi_ref(f'{obj.attr}')\n")
    with pytest.raises(ValueError, match="not a compile-time scalar"):
        compiled.materialize()


def test_reject_ref_fstring_with_function_call_part() -> None:
    compiled = astichi.compile("value = astichi_ref(f'{make_name()}')\n")
    with pytest.raises(ValueError, match="not a compile-time scalar"):
        compiled.materialize()


def test_reject_ref_positional_and_external_combined() -> None:
    with pytest.raises(ValueError, match="either"):
        astichi.compile("value = astichi_ref('foo', external=path)\n")


def test_reject_ref_path_with_invalid_identifier_segment() -> None:
    compiled = astichi.compile("value = astichi_ref('a.1b')\n")
    with pytest.raises(ValueError, match="not a valid Python identifier"):
        compiled.materialize()


# ---------------------------------------------------------------------------
# Integration: doesn't disturb other markers
# ---------------------------------------------------------------------------


def test_ref_coexists_with_keep_and_export() -> None:
    rendered = _materialized(
        """
astichi_keep(self)
result = astichi_ref('self.f0')
astichi_export(result)
"""
    )
    assert "result = self.f0" in rendered
    assert "astichi_keep" not in rendered
    assert "astichi_export" not in rendered


def test_ref_lowering_runs_before_hygiene_so_chain_head_is_subject_to_rename() -> None:
    # `result` is bound at module scope; `astichi_ref('result')` lowers
    # to a bare Name(Load) for `result`, which hygiene leaves alone
    # because there's no shadowing collision. The point of this test is
    # to exercise the post-lowering classification path.
    rendered = _materialized(
        """
result = 1
alias = astichi_ref('result')
"""
    )
    assert "alias = result" in rendered
