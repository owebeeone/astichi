"""Tests for `astichi.lowering.unroll.unroll_tree`."""

from __future__ import annotations

import ast
import textwrap

import pytest

from astichi.lowering.unroll import unroll_tree


def _unroll(source: str) -> str:
    tree = ast.parse(textwrap.dedent(source))
    unrolled = unroll_tree(tree)
    return ast.unparse(unrolled).strip()


def _lines(source: str) -> list[str]:
    return [line.strip() for line in _unroll(source).splitlines() if line.strip()]


# ---- no-op cases --------------------------------------------------------


def test_unroll_empty_module() -> None:
    assert _unroll("") == ""


def test_unroll_no_loops_returns_equivalent() -> None:
    src = "x = 1\ny = x + 2"
    assert _unroll(src) == src


def test_unroll_regular_for_is_untouched() -> None:
    src = "for i in range(3):\n    print(i)"
    assert _unroll(src) == src


# ---- basic expansion ----------------------------------------------------


def test_unroll_single_loop_int_tuple() -> None:
    result = _lines(
        """
        for x in astichi_for((10, 20, 30)):
            f(x)
        """
    )
    assert result == ["f(10)", "f(20)", "f(30)"]


def test_unroll_hole_gets_iter_suffix() -> None:
    result = _lines(
        """
        for x in astichi_for((10, 20)):
            astichi_hole(slot)
        """
    )
    assert result == ["astichi_hole(slot__iter_0)", "astichi_hole(slot__iter_1)"]


def test_unroll_empty_domain_removes_loop() -> None:
    assert _unroll("for x in astichi_for(()):\n    f(x)") == ""


def test_unroll_range_domain() -> None:
    result = _lines(
        """
        for i in astichi_for(range(3)):
            astichi_hole(slot)
        """
    )
    assert result == [
        "astichi_hole(slot__iter_0)",
        "astichi_hole(slot__iter_1)",
        "astichi_hole(slot__iter_2)",
    ]


def test_unroll_tuple_unpacking() -> None:
    result = _lines(
        """
        for x, y in astichi_for(((1, 2), (3, 4))):
            f(x, y)
        """
    )
    assert result == ["f(1, 2)", "f(3, 4)"]


def test_unroll_substitutes_at_nested_positions() -> None:
    result = _lines(
        """
        for x in astichi_for((10, 20)):
            arr[x] = x + 1
        """
    )
    assert result == ["arr[10] = 10 + 1", "arr[20] = 20 + 1"]


def test_unroll_preserves_store_targets() -> None:
    # `x` as a store target in a nested `for` is untouched; body references
    # resolve to the inner loop's binding, so the outer sub halts there.
    result = _lines(
        """
        for x in astichi_for((1,)):
            for x in other:
                use(x)
        """
    )
    assert result == ["for x in other:", "use(x)"]


# ---- nested astichi_for -------------------------------------------------


def test_unroll_nested_loops_with_dependent_domain() -> None:
    result = _lines(
        """
        for x, y in astichi_for(((1, 2), (2, 1))):
            astichi_hole(first)
            for a in astichi_for(range(y)):
                astichi_hole(second)
        """
    )
    assert result == [
        "astichi_hole(first__iter_0)",
        "astichi_hole(second__iter_0_0)",
        "astichi_hole(second__iter_0_1)",
        "astichi_hole(first__iter_1)",
        "astichi_hole(second__iter_1_0)",
    ]


def test_unroll_nested_same_variable_shadows() -> None:
    result = _lines(
        """
        for x in astichi_for((1, 2)):
            for x in astichi_for((10, 20)):
                astichi_hole(slot)
        """
    )
    # Outer renames holes once per outer iter; inner renames append `_<j>`.
    assert result == [
        "astichi_hole(slot__iter_0_0)",
        "astichi_hole(slot__iter_0_1)",
        "astichi_hole(slot__iter_1_0)",
        "astichi_hole(slot__iter_1_1)",
    ]


# ---- shadowing scopes ---------------------------------------------------


def test_unroll_halts_at_function_parameter() -> None:
    result = _lines(
        """
        for x in astichi_for((5,)):
            def f(x):
                return x
        """
    )
    assert result == ["def f(x):", "return x"]


def test_unroll_halts_at_lambda_parameter() -> None:
    result = _lines(
        """
        for x in astichi_for((5,)):
            g = lambda x: x + 1
        """
    )
    assert result == ["g = lambda x: x + 1"]


def test_unroll_halts_at_comprehension_target() -> None:
    result = _lines(
        """
        for x in astichi_for((5,)):
            pairs = [x + 1 for x in items]
        """
    )
    assert result == ["pairs = [x + 1 for x in items]"]


def test_unroll_halts_at_class_body() -> None:
    result = _lines(
        """
        for x in astichi_for((5,)):
            class C:
                x = 1
                y = x
        """
    )
    assert result == ["class C:", "x = 1", "y = x"]


def test_unroll_substitutes_into_function_default() -> None:
    result = _lines(
        """
        for x in astichi_for((7,)):
            def f(a=x):
                return a
        """
    )
    # Defaults evaluate in the enclosing scope, so x is substituted.
    assert result == ["def f(a=7):", "return a"]


def test_unroll_substitutes_into_comprehension_iter() -> None:
    result = _lines(
        """
        for x in astichi_for((3,)):
            pairs = [a for a in range(x)]
        """
    )
    assert result == ["pairs = [a for a in range(3)]"]


# ---- accumulator (shared scope) ----------------------------------------


def test_unroll_preserves_shared_scope_accumulator() -> None:
    result = _lines(
        """
        total = 0
        for x in astichi_for((1, 2, 3)):
            total = total + x
        """
    )
    assert result == [
        "total = 0",
        "total = total + 1",
        "total = total + 2",
        "total = total + 3",
    ]


# ---- rejections ---------------------------------------------------------


def test_reject_same_scope_rebind_assign() -> None:
    with pytest.raises(ValueError, match="may not be rebound"):
        _unroll(
            """
            for x in astichi_for((1,)):
                x = 99
            """
        )


def test_reject_same_scope_rebind_augassign() -> None:
    with pytest.raises(ValueError, match="may not be rebound"):
        _unroll(
            """
            for x in astichi_for((1,)):
                x += 1
            """
        )


def test_reject_same_scope_rebind_walrus() -> None:
    with pytest.raises(ValueError, match="may not be rebound"):
        _unroll(
            """
            for x in astichi_for((1,)):
                y = (x := 5)
            """
        )


def test_reject_hole_uses_loop_variable() -> None:
    with pytest.raises(ValueError, match="loop variable 'x'"):
        _unroll(
            """
            for x in astichi_for((1,)):
                astichi_hole(x)
            """
        )


def test_reject_export_in_body() -> None:
    with pytest.raises(ValueError, match="astichi_export"):
        _unroll(
            """
            for x in astichi_for((1,)):
                astichi_export(out)
            """
        )


def test_reject_keep_in_body() -> None:
    with pytest.raises(ValueError, match="astichi_keep"):
        _unroll(
            """
            for x in astichi_for((1,)):
                astichi_keep(name)
            """
        )


def test_reject_bind_external_in_body() -> None:
    with pytest.raises(ValueError, match="astichi_bind_external"):
        _unroll(
            """
            for x in astichi_for((1,)):
                astichi_bind_external(items)
            """
        )


def test_reject_insert_call_in_body() -> None:
    with pytest.raises(ValueError, match="astichi_insert"):
        _unroll(
            """
            for x in astichi_for((1,)):
                v = astichi_insert(slot, 42)
            """
        )


def test_reject_nonliteral_domain() -> None:
    with pytest.raises(ValueError, match="domain"):
        _unroll(
            """
            for x in astichi_for(items):
                f(x)
            """
        )


def test_reject_else_clause() -> None:
    with pytest.raises(ValueError, match="else"):
        _unroll(
            """
            for x in astichi_for((1,)):
                f(x)
            else:
                done()
            """
        )


def test_reject_async_for_with_astichi_for() -> None:
    src = textwrap.dedent(
        """
        async def h():
            async for x in astichi_for((1,)):
                f(x)
        """
    )
    with pytest.raises(ValueError, match="async for"):
        unroll_tree(ast.parse(src))
