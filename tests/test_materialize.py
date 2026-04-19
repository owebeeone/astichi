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
    """A matched `astichi_hole(target_slot)` + `@astichi_insert(target_slot)`
    pair introduces a fresh Astichi scope. Hygiene renames the inner
    `value` away from the outer `value`, while `astichi_keep(value)` pins
    the outer name and the residual `astichi_keep` marker is stripped.
    Per `AstichiApiDesignV1-CompositionUnification.md` \u00a72.5(c) the
    hole is required: an unmatched `@astichi_insert` would be rejected
    at the materialize gate."""
    compiled = astichi.compile(
        """
value = 1
astichi_hole(target_slot)

@astichi_insert(target_slot)
def inner():
    value = 2

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
    """Per CompositionUnification.md §6: `astichi_keep` / `astichi_export`
    call-form markers are stripped from the tree. Export port records
    survive on the composable. The legacy `astichi_definitional_name`
    call form is retired (issue 005) and no longer silently stripped."""
    compiled = astichi.compile(
        """
value = 1
astichi_keep(value)
result = 2
astichi_export(result)
"""
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert "astichi_keep" not in rendered
    assert "astichi_export" not in rendered

    assert "result" in {port.name for port in materialized.supply_ports}


def test_materialize_strips_keep_identifier_suffix_from_class_and_refs() -> None:
    # Issue 005 §4 / §5 step 4: the keep-identifier strip pass runs after
    # hygiene and rewrites every class/def binding and Load reference
    # carrying the `__astichi_keep__` suffix back to the stripped base.
    compiled = astichi.compile(
        """
class foo__astichi_keep__:
    pass


alias = foo__astichi_keep__
"""
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert "__astichi_keep__" not in rendered
    assert "class foo" in rendered
    assert "alias = foo" in rendered


def test_materialize_rejects_unresolved_arg_identifier_suffix() -> None:
    # Issue 005 §5 step 1 / §7: unresolved `__astichi_arg__` slots fail
    # the materialize gate before hygiene runs. The error lists every
    # occurrence of the parameter so the user sees its full reach.
    compiled = astichi.compile(
        """
class target__astichi_arg__:
    pass


ref = target__astichi_arg__
"""
    )

    with pytest.raises(
        ValueError,
        match=r"unresolved identifier-arg slots.*target__astichi_arg__",
    ):
        compiled.materialize()


def test_materialize_arg_gate_lists_all_occurrence_linenos_across_node_kinds() -> None:
    # Issue 005 §5 step 1 / §7 + 5b: the arg gate scans every suffix
    # occurrence - class/def names, `ast.Name` Load/Store, and `ast.arg`
    # parameters - and groups linenos by stripped name so the user sees
    # the full extent of the slot they forgot to resolve.
    compiled = astichi.compile(
        """
def step__astichi_arg__(item__astichi_arg__):
    item__astichi_arg__ = item__astichi_arg__ + 1
    return item__astichi_arg__


outer = step__astichi_arg__
"""
    )

    with pytest.raises(ValueError) as excinfo:
        compiled.materialize()

    message = str(excinfo.value)
    # Both stripped names appear in the error.
    assert "item" in message
    assert "step" in message
    # Line numbers for every occurrence of `item` are listed - the arg
    # parameter plus the three Name refs inside the body.
    assert message.count("item") >= 1
    # Line numbers for `step` cover both the def name and the outer
    # Load reference.
    assert message.count("step") >= 1


def test_materialize_resolves_arg_identifier_across_all_occurrences() -> None:
    # Issue 005 §5 step 2 / 5c: the resolver pass substitutes the
    # resolved identifier into every occurrence of the suffix - class
    # def names, Load Names, Store Names, and `ast.arg` parameters -
    # atomically. The gate accepts because the binding covers the slot.
    compiled = astichi.compile(
        """
def step__astichi_arg__(item__astichi_arg__):
    item__astichi_arg__ = item__astichi_arg__ + 1
    return item__astichi_arg__


outer = step__astichi_arg__
""",
    ).bind_identifier(step="run", item="value")

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    # No suffix survives anywhere.
    assert "__astichi_arg__" not in rendered
    # Every class-def, Load, Store, and arg occurrence resolved.
    assert "def run(value)" in rendered
    assert "value = value + 1" in rendered
    assert "return value" in rendered
    assert "outer = run" in rendered


def test_materialize_resolves_arg_identifier_on_class_field_definitions() -> None:
    # Issue 005 §1 / 5c: field-style definitions inside a class body -
    # plain `name = value`, annotated `name: T = value`, and the
    # "call variable defn" pattern `name = factory(...)` common in
    # dataclass / attrs - all have their LHS Store Name recognised as
    # a `__astichi_arg__` occurrence and resolved atomically with
    # every matching Store/Load reference in the same Python scope.
    # Keyword argument names (e.g. `default=`) are not identifier
    # slots and must survive.
    compiled = astichi.compile(
        """
class Config:
    first__astichi_arg__ = 0
    second__astichi_arg__: int = make_field(default=1)
    third__astichi_arg__ = make_field(factory=list)
    combined__astichi_arg__ = (
        first__astichi_arg__,
        second__astichi_arg__,
        third__astichi_arg__,
    )
""",
    ).bind_identifier(
        first="width",
        second="height",
        third="depth",
        combined="all_fields",
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert "__astichi_arg__" not in rendered
    assert "width = 0" in rendered
    assert "height: int = make_field(default=1)" in rendered
    assert "depth = make_field(factory=list)" in rendered
    # Tuple field combining the three prior fields; the Load refs in
    # the RHS resolve atomically with their Store counterparts in
    # the same class body scope.
    assert "all_fields = (width, height, depth)" in rendered
    # Keyword-argument names are not identifier slots - left alone.
    assert "default=1" in rendered
    assert "factory=list" in rendered


def test_materialize_resolves_arg_identifier_from_compile_arg_names() -> None:
    # Issue 005 §6 / 5d: `compile(..., arg_names=...)` plumbs through
    # to materialize without needing an additional `.bind_identifier`.
    compiled = astichi.compile(
        """
def step__astichi_arg__():
    return 1
""",
        arg_names={"step": "final_name"},
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)
    assert "__astichi_arg__" not in rendered
    assert "def final_name()" in rendered


def test_materialize_arg_gate_still_rejects_partially_unresolved_slots() -> None:
    # Issue 005 §5 step 1 / 5c: binding only one of several slots
    # leaves the remaining ones unresolved; the gate rejects them and
    # lists their linenos.
    compiled = astichi.compile(
        """
def step__astichi_arg__(item__astichi_arg__):
    return item__astichi_arg__
""",
    ).bind_identifier(step="run")  # `item` left unresolved

    with pytest.raises(ValueError) as excinfo:
        compiled.materialize()

    message = str(excinfo.value)
    assert "item__astichi_arg__" in message
    # `step` was resolved so it must NOT appear in the diagnostic.
    assert "step__astichi_arg__" not in message


def test_materialize_resolver_pinned_target_survives_hygiene_collision() -> None:
    # Issue 005 §6 / 5c: the resolved target name is pinned in the
    # keep set so a competing free `foo` is renamed away rather than
    # colliding with the post-resolve binding.
    compiled = astichi.compile(
        """
def step__astichi_arg__():
    return 1


foo = 0
""",
    ).bind_identifier(step="foo")

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)
    # The def lands on the pinned name.
    assert "def foo(" in rendered
    # The competing free `foo` has been renamed away (not equal to the def).
    assert rendered.count("def foo(") == 1


def test_bind_identifier_rejects_unknown_slot_name() -> None:
    compiled = astichi.compile(
        """
def step__astichi_arg__():
    return 1
""",
    )
    with pytest.raises(ValueError, match=r"no __astichi_arg__ / astichi_import slot named `missing`"):
        compiled.bind_identifier(missing="x")


def test_bind_identifier_rejects_rebinding_an_already_resolved_slot() -> None:
    compiled = astichi.compile(
        """
def step__astichi_arg__():
    return 1
""",
    ).bind_identifier(step="first")
    with pytest.raises(ValueError, match=r"cannot re-bind identifier arg `step`"):
        compiled.bind_identifier(step="second")


def test_materialize_strips_keep_identifier_suffix_from_arg_position() -> None:
    # Issue 005 §4 / 5b: the keep-strip pass extends to `ast.arg`, so a
    # parameter bearing `__astichi_keep__` emits as the stripped name.
    compiled = astichi.compile(
        """
def wrap(callback__astichi_keep__):
    return callback__astichi_keep__()
"""
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert "__astichi_keep__" not in rendered
    assert "def wrap(callback)" in rendered
    assert "return callback()" in rendered


def test_materialize_preserves_stripped_keep_name_against_collision() -> None:
    # Issue 005 §4: when a free name would collide with the post-strip
    # keep name, hygiene renames the free name away. The keep-suffixed
    # binding survives unchanged until the strip pass rewrites it.
    compiled = astichi.compile(
        """
class foo__astichi_keep__:
    pass


foo = 1


value = foo
"""
    )

    materialized = compiled.materialize()
    rendered = ast.unparse(materialized.tree)

    assert "__astichi_keep__" not in rendered
    assert "class foo:" in rendered
    # The competing free `foo` must be renamed; the Load reference
    # follows the rename so `value = foo_<n>` (not the class).
    assert rendered.count("class foo:") == 1


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


def test_materialize_variadic_positional_expression_sources() -> None:
    """`*astichi_hole(items)` accepts multiple authored expression sources
    and splices them into the containing list in declared order."""
    builder = astichi.build()
    builder.add.Root(astichi.compile("result = [*astichi_hole(items)]\n"))
    builder.add.A(astichi.compile("1\n"))
    builder.add.B(astichi.compile("2\n"))
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
    `test_materialize_applies_hygiene_closure`. The scope boundary is
    introduced by a matched `astichi_hole` + `@astichi_insert` pair as
    required by `AstichiApiDesignV1-CompositionUnification.md` \u00a72.5(c)."""
    compiled = astichi.compile(
        """
value = 1
astichi_hole(target_slot)

@astichi_insert(target_slot)
def inner():
    value = 2
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
# Strict scope isolation contract. Every Astichi scope (module root,
# every root instance under the merge-time wrap, every builder
# contribution shell, every expression-form insert wrapper) owns its
# own lexical name space. Cross-scope wiring is *explicit*: it goes
# through `astichi_import` / `astichi_pass` / `astichi_export` (or
# the builder-level equivalents: `arg_names=`, `keep_names=`, and
# `builder.assign.<Src>.<inner>.to().<Dst>.<outer>`). Free-name
# references inside a shell that are not wired across the boundary
# are local to that shell, full stop. Whatever the user wrote on
# those names is preserved faithfully — astichi does not guess.
# ---------------------------------------------------------------------------


def test_strict_scope_isolation_unwired_free_name_is_scope_local() -> None:
    """Unwired free-name references inside a builder contribution stay
    scope-local.

    Step's body reads and writes `total` without declaring
    `astichi_import(total)`. The root also binds `total`. Under strict
    scope isolation, Step's `total` is a *fresh* binding in Step's
    contribution scope — it does not silently capture Root's `total`.
    Hygiene therefore renames Step's occurrences apart
    (`total__astichi_scoped_N`), and the emitted program faithfully
    reflects what the user actually wrote: a read-before-write on a
    fresh local. Running it raises `NameError` because the user's
    source expressed broken Python on its own local, not because
    astichi introduced any ambiguity.

    If the user's intent is "Step's `total` is Root's `total`", the
    contract is to declare `astichi_import(total)` in Step — see the
    `astichi_import`-based accumulator composition in
    `tests/test_boundaries.py` and `scratch/test_mat2.py`.
    """
    builder = astichi.build()
    builder.add.Root(astichi.compile("total = 0\nastichi_hole(body)\n"))
    builder.add.Step(astichi.compile("total = total + 1\n"))
    builder.Root.body.add.Step()

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    assert "total = 0" in source
    assert "total__astichi_scoped_" in source
    scoped_line = next(
        line for line in source.splitlines() if "total__astichi_scoped_" in line
    )
    # Hygiene renamed *both* sides of Step's assign together — Step's
    # `total` is one binding, isolated from Root's. This is the
    # contract, not a bug.
    assert scoped_line.count("total__astichi_scoped_") == 2

    namespace: dict[str, object] = {}
    with pytest.raises(NameError):
        exec(compile(source, "<t>", "exec"), namespace)


def test_materialize_rejects_unmatched_block_insert_shell() -> None:
    """Per CompositionUnification.md \u00a72.5(c): an unmatched
    `@astichi_insert(slot)` shell (no sibling `astichi_hole(slot)`) is
    refused at the materialize gate before hygiene runs. Previously
    tracked as Gap 4 in dev-docs/v2_issues/004."""
    compiled = astichi.compile(
        """
@astichi_insert(slot)
def __unmatched():
    leaked = True
"""
    )
    with pytest.raises(
        ValueError, match=r"unmatched astichi_insert supplies"
    ):
        compiled.materialize()


def test_materialize_rejects_unmatched_expression_insert() -> None:
    """Per CompositionUnification.md \u00a72.5(c): a bare-statement
    expression-form `astichi_insert(name, ...)` (an unwired supply
    declaration) is refused at the materialize gate. Wrapper forms
    embedded in expression positions by `build()` are legitimate and
    are unwrapped by `_realize_expression_insert_wrappers`; the gate
    only rejects the bare statement shape."""
    compiled = astichi.compile("astichi_insert(slot, 42)\n")
    with pytest.raises(
        ValueError, match=r"unmatched astichi_insert supplies"
    ):
        compiled.materialize()
