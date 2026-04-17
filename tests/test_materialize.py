from __future__ import annotations

import ast

import pytest

import astichi
from astichi.model import BasicComposable


def test_materialize_produces_valid_composable() -> None:
    compiled = astichi.compile("value = 1\n")

    result = compiled.materialize()

    assert isinstance(result, BasicComposable)
    assert "value = 1" in ast.unparse(result.tree)


def test_materialize_rejects_unresolved_holes() -> None:
    compiled = astichi.compile("astichi_hole(body)\n")

    with pytest.raises(ValueError, match="mandatory holes remain unresolved: body"):
        compiled.materialize()


def test_materialize_rejects_unresolved_bind_external_demands() -> None:
    compiled = astichi.compile("astichi_bind_external(fields)\nprint(fields)\n")

    with pytest.raises(
        ValueError,
        match=r"external binding for `fields` was not supplied; call composable.bind\(fields=\.\.\.\) before materializing\.",
    ):
        compiled.materialize()


def test_materialize_allows_fully_bound_composable() -> None:
    compiled = astichi.compile(
        """
astichi_bind_external(fields)
print(fields)
"""
    )

    bound = compiled.bind(fields=("a", "b"))
    materialized = bound.materialize()

    assert isinstance(materialized, BasicComposable)
    assert ast.unparse(materialized.tree) == "print(('a', 'b'))"


def test_materialize_applies_hygiene_closure() -> None:
    compiled = astichi.compile(
        """
value = 1

@astichi_insert(target_slot)
def inner():
    value = 2
    return value

result = astichi_keep(value)
"""
    )

    materialized = compiled.materialize()

    rendered = ast.unparse(materialized.tree)
    assert "value = 1" in rendered
    assert "result = value" in rendered
    assert "astichi_keep" not in rendered
    assert "value__astichi_scoped_" in rendered


def test_materialize_strips_residual_markers() -> None:
    """Per CompositionUnification.md §6: astichi_keep / astichi_export /
    astichi_definitional_name are stripped from the tree. Export port
    records survive on the composable."""
    compiled = astichi.compile(
        """
value = 1
astichi_keep(value)
result = 2
astichi_export(result)
astichi_definitional_name(result)
"""
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert "astichi_keep" not in rendered
    assert "astichi_export" not in rendered
    assert "astichi_definitional_name" not in rendered

    assert "result" in {port.name for port in materialized.supply_ports}


def test_materialize_allows_implied_demands() -> None:
    compiled = astichi.compile("value = missing_name\n")

    result = compiled.materialize()

    assert isinstance(result, BasicComposable)
    assert "missing_name" in ast.unparse(result.tree)


def test_add_contributions_get_isolated_scopes() -> None:
    """Per CompositionUnification.md §2.4: every .add() contribution is a
    fresh Astichi scope; colliding local names are renamed apart."""
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.add.StepA(astichi.compile("total = 0\n"))
    builder.add.StepB(astichi.compile("total = 1\n"))
    builder.Root.body.add.StepA(order=0)
    builder.Root.body.add.StepB(order=1)

    materialized = builder.build().materialize()
    rendered = ast.unparse(materialized.tree)

    assert "total = 0" in rendered
    assert "total__astichi_scoped_" in rendered
    assert "astichi_insert" not in rendered


def test_compose_build_round_trip_is_structurally_stable() -> None:
    """Per CompositionUnification.md §2.3: compile(c.emit()).tree structurally
    matches c.tree for pre-materialize composables."""
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(body)\n"))
    builder.add.Piece(astichi.compile("value = 42\n"))
    builder.Root.body.add.Piece()

    built = builder.build()
    emitted = built.emit(provenance=False)
    reingested = astichi.compile(emitted)

    assert ast.dump(reingested.tree) == ast.dump(built.tree)


def test_materialized_emit_is_executable() -> None:
    """Per CompositionUnification.md §2.2: materialize().emit() produces
    executable Python with no remaining marker call sites."""
    builder = astichi.build()
    builder.add.Root(astichi.compile("astichi_hole(setup)\nastichi_hole(body)\n"))
    builder.add.Setup(astichi.compile("a = 10\n"))
    builder.add.Step(astichi.compile("b = 20\n"))
    builder.Root.setup.add.Setup()
    builder.Root.body.add.Step()

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    assert "astichi_hole" not in source
    assert "astichi_insert" not in source
    namespace: dict[str, object] = {}
    exec(compile(source, "<materialized>", "exec"), namespace)
    assert namespace["a"] == 10
    assert namespace["b"] == 20


# ---------------------------------------------------------------------------
# Matrix: bind-external scenarios
# ---------------------------------------------------------------------------


def test_materialize_bind_external_in_expression_position() -> None:
    """Bound external substitutes into arbitrary expression positions."""
    compiled = astichi.compile(
        """
astichi_bind_external(factor)
result = (factor, factor * 2, [factor, factor + 1])
"""
    )

    materialized = compiled.bind(factor=7).materialize()
    rendered = ast.unparse(materialized.tree)

    assert rendered.strip() == "result = (7, 7 * 2, [7, 7 + 1])"
    namespace: dict[str, object] = {}
    exec(compile(materialized.emit(provenance=False), "<t>", "exec"), namespace)
    assert namespace["result"] == (7, 14, [7, 8])


def test_materialize_bind_external_with_multiple_names() -> None:
    """Multiple binds in one compose resolve independently."""
    compiled = astichi.compile(
        """
astichi_bind_external(a)
astichi_bind_external(b)
pair = (a, b)
"""
    )

    materialized = compiled.bind(a=1, b="x").materialize()

    namespace: dict[str, object] = {}
    exec(compile(materialized.emit(provenance=False), "<t>", "exec"), namespace)
    assert namespace["pair"] == (1, "x")


# ---------------------------------------------------------------------------
# Matrix: source-level @astichi_insert scenarios
# ---------------------------------------------------------------------------


def test_materialize_source_level_insert_matches_source_hole() -> None:
    """A source `@astichi_insert(slot)` paired with `astichi_hole(slot)`
    flattens to the shell body at the hole position."""
    compiled = astichi.compile(
        """
astichi_hole(slot)

@astichi_insert(slot)
def __piece():
    computed = 7
"""
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert rendered.strip() == "computed = 7"


def test_materialize_merges_multiple_source_level_inserts_in_order() -> None:
    """Two source-level `@astichi_insert` shells to the same hole splice in
    `order=` ascending order, source position breaking ties."""
    compiled = astichi.compile(
        """
astichi_hole(slot)

@astichi_insert(slot, order=0)
def __first():
    step_a = 1

@astichi_insert(slot, order=1)
def __second():
    step_b = 2
"""
    )

    rendered = ast.unparse(compiled.materialize().tree).strip()
    assert rendered == "step_a = 1\nstep_b = 2"


# ---------------------------------------------------------------------------
# Matrix: expression-insert shapes
# ---------------------------------------------------------------------------


def test_materialize_variadic_positional_expression_insert() -> None:
    """`*astichi_hole(items)` accepts multiple expression-insert sources
    and splices them into the containing list in declared order."""
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = [*astichi_hole(items)]\n"))
    builder.add.A(astichi.compile("astichi_insert(items, 1)\n"))
    builder.add.B(astichi.compile("astichi_insert(items, 2)\n"))
    builder.Root.items.add.A(order=0)
    builder.Root.items.add.B(order=1)

    materialized = builder.build().materialize()
    rendered = ast.unparse(materialized.tree).strip()

    assert rendered == "result = [1, 2]"
    namespace: dict[str, object] = {}
    exec(compile(materialized.emit(provenance=False), "<t>", "exec"), namespace)
    assert namespace["result"] == [1, 2]


# ---------------------------------------------------------------------------
# Matrix: bind + insert combination (end-to-end)
# ---------------------------------------------------------------------------


def test_materialize_bind_plus_block_insert_end_to_end() -> None:
    """bind → build → materialize → emit → exec pipeline with a bound
    external used by the root and a block insert supplied via `.add()`."""
    root_src = """
astichi_bind_external(seed)
accumulator = seed
astichi_hole(body)
"""
    step_src = "step_value = 42\n"

    root = astichi.compile(root_src).bind(seed=100)

    builder = astichi.build()
    builder.add.Root(root)
    builder.add.Step(astichi.compile(step_src))
    builder.Root.body.add.Step()

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    namespace: dict[str, object] = {}
    exec(compile(source, "<t>", "exec"), namespace)
    assert namespace["accumulator"] == 100
    assert namespace["step_value"] == 42


# ---------------------------------------------------------------------------
# Matrix: astichi_keep preserves a name that hygiene would otherwise rename
# ---------------------------------------------------------------------------


def test_materialize_without_keep_renames_colliding_outer_name() -> None:
    """Baseline for the `astichi_keep` matrix row: without `astichi_keep`,
    hygiene renames the inner-scope collision but leaves the outer binding
    alone. This pins the hygiene contrast used by
    `test_materialize_applies_hygiene_closure`."""
    compiled = astichi.compile(
        """
value = 1

@astichi_insert(target_slot)
def inner():
    value = 2
    return value
"""
    )

    rendered = ast.unparse(compiled.materialize().tree)

    assert "value = 1" in rendered
    assert "value__astichi_scoped_1 = 2" in rendered


# ---------------------------------------------------------------------------
# Matrix: export supply port survives materialize with declared public name
# ---------------------------------------------------------------------------


def test_materialize_export_supply_port_round_trips() -> None:
    """Per CompositionUnification.md §6: `astichi_export(name)` is stripped
    from the tree but its supply-port record survives on the composable."""
    compiled = astichi.compile(
        """
value = 42
astichi_export(value)
"""
    )

    materialized = compiled.materialize()

    export_names = {port.name for port in materialized.supply_ports}
    assert "value" in export_names

    rendered = ast.unparse(materialized.tree)
    assert "astichi_export" not in rendered
    assert "value = 42" in rendered


# ---------------------------------------------------------------------------
# Soundness gaps tracked by dev-docs/v2_issues/004-materialize-free-name-
# soundness.md. These are xfail regressions so we notice when the gap
# closes (and must then convert to passing assertions).
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Gap 3 (issue 004): `total = total + 1` inside a fresh Astichi "
        "scope renames both sides together, producing a renamed local "
        "that reads itself before being written. Emitted code raises "
        "UnboundLocalError at runtime."
    ),
)
def test_materialize_gap3_self_ref_rename_xfail() -> None:
    builder = astichi.build()
    builder.add.Root(astichi.compile("total = 0\nastichi_hole(body)\n"))
    builder.add.Step(astichi.compile("total = total + 1\n"))
    builder.Root.body.add.Step()

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    namespace: dict[str, object] = {}
    exec(compile(source, "<t>", "exec"), namespace)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Gap 4 (issue 004): an unmatched `@astichi_insert(slot)` shell "
        "without a sibling `astichi_hole(slot)` survives materialize "
        "instead of raising per CompositionUnification.md §6 "
        "(invariant violation)."
    ),
)
def test_materialize_gap4_unmatched_insert_shell_xfail() -> None:
    compiled = astichi.compile(
        """
@astichi_insert(slot)
def __unmatched():
    leaked = True
"""
    )
    with pytest.raises(ValueError):
        compiled.materialize()
