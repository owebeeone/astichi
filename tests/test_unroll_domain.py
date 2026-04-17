from __future__ import annotations

import ast

import pytest

from astichi.lowering.unroll_domain import resolve_domain


def _domain(source: str) -> ast.expr:
    """Parse `astichi_for(<source>)` and return the domain expression."""
    tree = ast.parse(f"astichi_for({source})", mode="eval")
    call = tree.body
    assert isinstance(call, ast.Call) and len(call.args) == 1
    return call.args[0]


def test_empty_tuple_yields_no_iterations() -> None:
    assert resolve_domain(_domain("()")) == []


def test_empty_list_yields_no_iterations() -> None:
    assert resolve_domain(_domain("[]")) == []


def test_tuple_of_ints() -> None:
    assert resolve_domain(_domain("(10, 20, 30)")) == [10, 20, 30]


def test_list_of_ints() -> None:
    assert resolve_domain(_domain("[10, 20, 30]")) == [10, 20, 30]


def test_tuple_of_strings() -> None:
    assert resolve_domain(_domain("('a', 'b', 'c')")) == ["a", "b", "c"]


def test_mixed_scalar_literals() -> None:
    assert resolve_domain(_domain("(1, 'a', 1.5, True, None)")) == [
        1,
        "a",
        1.5,
        True,
        None,
    ]


def test_nested_tuples_for_unpacking_targets() -> None:
    assert resolve_domain(_domain("((1, 2), (3, 4), (5, 6))")) == [
        (1, 2),
        (3, 4),
        (5, 6),
    ]


def test_nested_lists_are_preserved_as_tuples() -> None:
    assert resolve_domain(_domain("([1, 2], [3, 4])")) == [(1, 2), (3, 4)]


def test_unary_minus_literal_in_tuple() -> None:
    assert resolve_domain(_domain("(-1, 0, 1)")) == [-1, 0, 1]


def test_unary_minus_float_in_tuple() -> None:
    assert resolve_domain(_domain("(-1.5, 2.5)")) == [-1.5, 2.5]


def test_range_single_arg() -> None:
    assert resolve_domain(_domain("range(4)")) == [0, 1, 2, 3]


def test_range_two_args() -> None:
    assert resolve_domain(_domain("range(2, 5)")) == [2, 3, 4]


def test_range_three_args() -> None:
    assert resolve_domain(_domain("range(0, 10, 3)")) == [0, 3, 6, 9]


def test_range_negative_step() -> None:
    assert resolve_domain(_domain("range(5, 0, -1)")) == [5, 4, 3, 2, 1]


def test_range_negative_bounds() -> None:
    assert resolve_domain(_domain("range(-2, 2)")) == [-2, -1, 0, 1]


def test_range_zero_iterations() -> None:
    assert resolve_domain(_domain("range(0)")) == []


def test_bare_name_rejected() -> None:
    with pytest.raises(ValueError, match=r"bare name 'items'"):
        resolve_domain(_domain("items"))


def test_unknown_call_rejected() -> None:
    with pytest.raises(ValueError, match=r"call to list\(\)"):
        resolve_domain(_domain("list((1, 2, 3))"))


def test_range_zero_args_rejected() -> None:
    with pytest.raises(ValueError, match=r"1 to 3 positional arguments"):
        resolve_domain(_domain("range()"))


def test_range_four_args_rejected() -> None:
    with pytest.raises(ValueError, match=r"1 to 3 positional arguments"):
        resolve_domain(_domain("range(1, 2, 3, 4)"))


def test_range_non_literal_arg_rejected() -> None:
    with pytest.raises(ValueError, match=r"range argument 0 must be"):
        resolve_domain(_domain("range(n)"))


def test_range_float_arg_rejected() -> None:
    with pytest.raises(ValueError, match=r"range argument 0 must be"):
        resolve_domain(_domain("range(1.5)"))


def test_range_bool_arg_rejected() -> None:
    with pytest.raises(ValueError, match=r"range argument 0 must be"):
        resolve_domain(_domain("range(True)"))


def test_range_kwargs_rejected() -> None:
    tree = ast.parse("range(start=0, stop=5)", mode="eval")
    with pytest.raises(ValueError, match=r"keyword arguments"):
        resolve_domain(tree.body)


def test_list_comprehension_rejected() -> None:
    with pytest.raises(ValueError, match=r"comprehension"):
        resolve_domain(_domain("[x for x in items]"))


def test_generator_expression_rejected() -> None:
    tree = ast.parse("(x for x in items)", mode="eval")
    with pytest.raises(ValueError, match=r"comprehension"):
        resolve_domain(tree.body)


def test_non_literal_element_in_tuple_rejected() -> None:
    with pytest.raises(ValueError, match=r"bare name 'x'"):
        resolve_domain(_domain("(1, x, 3)"))


def test_dict_literal_rejected() -> None:
    with pytest.raises(
        ValueError, match=r"literal tuple/list or range"
    ):
        resolve_domain(_domain("{1: 2}"))


def test_set_literal_rejected() -> None:
    with pytest.raises(
        ValueError, match=r"literal tuple/list or range"
    ):
        resolve_domain(_domain("{1, 2, 3}"))


def test_complex_literal_element_rejected() -> None:
    with pytest.raises(
        ValueError, match=r"literal tuple/list or range"
    ):
        resolve_domain(_domain("(1+2j,)"))


def test_bytes_literal_accepted() -> None:
    assert resolve_domain(_domain("(b'x', b'y')")) == [b"x", b"y"]
