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


def test_end_to_end_additive_composition_preserves_order() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
astichi_hole(init)
astichi_hole(body)
"""
        )
    )
    builder.add.Setup(astichi.compile("first = 1\n"))
    builder.add.Step1(astichi.compile("second = 2\n"))
    builder.add.Step2(astichi.compile("third = 3\n"))
    builder.Root.init.add.Setup()
    builder.Root.body.add.Step1(order=0)
    builder.Root.body.add.Step2(order=1)

    built = builder.build()
    materialized = built.materialize()

    rendered = ast.unparse(materialized.tree)
    assert "first = 1" in rendered
    assert "second = 2" in rendered
    assert "third = 3" in rendered
    assert rendered.index("first = 1") < rendered.index("second = 2")
    assert rendered.index("second = 2") < rendered.index("third = 3")
    assert "astichi_hole" not in rendered
    assert "astichi_insert" not in rendered


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
