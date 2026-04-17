"""Tests for the Astichi boundary markers (issue 006 6a + 6b)."""

from __future__ import annotations

import pytest

import astichi
from astichi.lowering import MARKERS_BY_NAME
from astichi.model.ports import IDENTIFIER


def test_import_and_pass_markers_are_registered() -> None:
    # Issue 006 6a: `astichi_import` and `astichi_pass` must be recognised
    # alongside the other call-form markers and self-report as
    # name-bearing identifier declarations.
    assert "astichi_import" in MARKERS_BY_NAME
    assert "astichi_pass" in MARKERS_BY_NAME
    assert MARKERS_BY_NAME["astichi_import"].is_name_bearing() is True
    assert MARKERS_BY_NAME["astichi_pass"].is_name_bearing() is True


def test_compile_recognizes_module_level_boundary_markers() -> None:
    compiled = astichi.compile(
        """
astichi_import(outer_name)
astichi_pass(inner_name)

result = outer_name + inner_name
inner_name = 0
"""
    )

    boundary_markers = [
        marker
        for marker in compiled.markers
        if marker.source_name in ("astichi_import", "astichi_pass")
    ]
    kinds = [(m.source_name, m.name_id) for m in boundary_markers]
    assert kinds == [
        ("astichi_import", "outer_name"),
        ("astichi_pass", "inner_name"),
    ]


def test_compile_emits_identifier_ports_for_boundary_markers() -> None:
    # Issue 006 6a: `astichi_import(name)` surfaces as an IDENTIFIER
    # demand port on the piece, `astichi_pass(name)` as an IDENTIFIER
    # supply port.
    compiled = astichi.compile(
        """
astichi_import(dep)
astichi_pass(result)

result = dep
"""
    )

    dep_port = next(
        port for port in compiled.demand_ports if port.name == "dep"
    )
    assert dep_port.shape is IDENTIFIER
    assert dep_port.placement == "identifier"
    assert "import" in dep_port.sources

    result_port = next(
        port for port in compiled.supply_ports if port.name == "result"
    )
    assert result_port.shape is IDENTIFIER
    assert result_port.placement == "identifier"
    assert "pass" in result_port.sources


def test_placement_accepts_top_prefix_at_module_and_shell_scopes() -> None:
    # Issue 006 6a: the top-of-body prefix in both the module scope and
    # any `@astichi_insert`-decorated shell body is a legal position.
    astichi.compile(
        """
astichi_import(outer)
astichi_pass(top_result)

@astichi_insert(target)
def shell_block():
    astichi_import(shared)
    astichi_pass(nested_out)

    nested_out = shared + 1

top_result = 0
"""
    )


def test_placement_rejects_boundary_after_real_statement_in_module() -> None:
    # Issue 006 6a: boundary markers that appear after any real
    # statement in the module body break the top-prefix rule.
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(\.\.\.\) at line \d+ in module body: "
        r"boundary markers must form the top-of-body prefix",
    ):
        astichi.compile(
            """
x = 1
astichi_import(late)
"""
        )


def test_placement_rejects_boundary_nested_in_if_block() -> None:
    # Issue 006 6a: boundary markers inside a compound statement are
    # not at the top of any Astichi scope body.
    with pytest.raises(
        ValueError,
        match=r"astichi_pass\(\.\.\.\) at line \d+: must appear at the top of",
    ):
        astichi.compile(
            """
if True:
    astichi_pass(stray)
"""
        )


def test_placement_rejects_boundary_inside_non_shell_def() -> None:
    # Issue 006 6a: a plain (non-`@astichi_insert`) def does not open
    # an Astichi scope; markers inside it belong to the surrounding
    # Astichi scope and are therefore misplaced.
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(\.\.\.\) at line \d+: must appear at the top of",
    ):
        astichi.compile(
            """
def helper():
    astichi_import(leaked)
    return leaked
"""
        )


def test_placement_accepts_boundary_as_top_prefix_in_shell_but_rejects_after() -> None:
    # Issue 006 6a: inside a shell body, the prefix rule applies again —
    # markers after a real statement in the shell body are rejected,
    # not leaked through because the module-level prefix accepted them.
    with pytest.raises(
        ValueError,
        match=r"astichi_pass\(\.\.\.\) at line \d+ in shell 'block' body",
    ):
        astichi.compile(
            """
@astichi_insert(target)
def block():
    astichi_import(ok_prefix)
    ok_prefix
    astichi_pass(late_in_shell)
"""
        )


def test_placement_allows_multiple_prefix_boundary_statements() -> None:
    # Issue 006 6a: any number of contiguous import/pass statements at
    # the top of an Astichi scope are legal.
    astichi.compile(
        """
astichi_import(a)
astichi_import(b)
astichi_pass(c)
astichi_pass(d)

c = a
d = b
"""
    )


def test_placement_rejects_boundary_marker_as_decorator_or_nested_call() -> None:
    # Issue 006 6a: boundary calls must be statements; embedded in an
    # expression or as a decorator they are not declarations and are
    # rejected.
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(\.\.\.\) at line \d+",
    ):
        astichi.compile(
            """
result = astichi_import(bad_in_expr)
"""
        )


# ---------------------------------------------------------------------------
# 6b: hygiene pinning + interaction matrix
# ---------------------------------------------------------------------------


def test_hygiene_pins_import_and_pass_names_against_implied_demand() -> None:
    # Issue 006 6b: Load references to an imported/passed name inside
    # the scope must NOT be reclassified as implied SCALAR_EXPR demands
    # (the name is supplied across an Astichi scope boundary). Only the
    # IDENTIFIER-shape port sourced from the boundary marker survives.
    compiled = astichi.compile(
        """
astichi_import(dep)
astichi_pass(out)

out = dep + 1
"""
    )

    dep_sources = {
        port.sources
        for port in compiled.demand_ports
        if port.name == "dep"
    }
    # dep shows up exactly as the IDENTIFIER import demand; no implied
    # SCALAR_EXPR clone was added.
    assert dep_sources == {frozenset({"import"})}
    # `out` is not classified as an implied demand either.
    assert not any(port.name == "out" for port in compiled.demand_ports)


def test_interaction_matrix_rejects_import_and_pass_on_same_name() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(x\).*conflicts with astichi_pass\(x\)",
    ):
        astichi.compile(
            """
astichi_import(x)
astichi_pass(x)
"""
        )


def test_interaction_matrix_rejects_import_and_keep_suffix_on_same_name() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(widget\).*__astichi_keep__ suffix\(widget\)",
    ):
        astichi.compile(
            """
astichi_import(widget)

class widget__astichi_keep__:
    pass
"""
        )


def test_interaction_matrix_rejects_import_and_arg_suffix_on_same_name() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(target\).*__astichi_arg__ suffix\(target\)",
    ):
        astichi.compile(
            """
astichi_import(target)

def target__astichi_arg__():
    return 1
"""
        )


def test_interaction_matrix_rejects_import_and_export_on_same_name() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(shared\).*astichi_export\(shared\)",
    ):
        astichi.compile(
            """
astichi_import(shared)

shared = 1
astichi_export(shared)
"""
        )


def test_interaction_matrix_allows_pass_alongside_keep_and_arg() -> None:
    # Issue 006 §9.2: `pass` may coexist with keep-suffix and
    # arg-suffix on the same name — the matrix gate does not reject.
    astichi.compile(
        """
astichi_pass(handler)
astichi_pass(knob)

class handler__astichi_keep__:
    pass


def knob__astichi_arg__():
    return 0
"""
    )


def test_interaction_matrix_allows_pass_plus_export_via_direct_gate_call() -> None:
    # Issue 006 §9.2: `pass + astichi_export` on the same name is
    # valid at the interaction-matrix level. We exercise the gate
    # directly because `pass` contributes an IDENTIFIER supply and
    # `export` contributes a SCALAR_EXPR supply for the same name;
    # the compile-time supply-port merge across distinct shapes is
    # a separate concern handled by 6c.
    import ast as _ast
    from astichi.lowering import (
        recognize_markers,
        validate_boundary_interaction_matrix,
    )

    tree = _ast.parse(
        """
astichi_pass(shared)

shared = 42
astichi_export(shared)
"""
    )
    markers = recognize_markers(tree)
    validate_boundary_interaction_matrix(tree, markers)


def test_interaction_matrix_is_scoped_per_astichi_scope() -> None:
    # Issue 006 §9.2: the forbidden combinations apply per-scope. An
    # import at module level + a keep-suffix inside an `@astichi_insert`
    # shell does not collide because they live in different Astichi
    # scopes.
    astichi.compile(
        """
astichi_import(widget)

widget

@astichi_insert(target)
def shell_block():
    class widget__astichi_keep__:
        pass
"""
    )


def test_interaction_matrix_rejects_same_scope_conflict_inside_shell() -> None:
    # ... but *within* the shell scope, the rule still applies.
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(widget\).*__astichi_keep__ suffix\(widget\)",
    ):
        astichi.compile(
            """
@astichi_insert(target)
def shell_block():
    astichi_import(widget)

    class widget__astichi_keep__:
        pass
"""
        )


# ---------------------------------------------------------------------------
# Issue 006 6c: import resolution + stripping + builder-edge arg_names.
# ---------------------------------------------------------------------------


_ACCUM_ROOT_SRC = """
total = 0
astichi_hole(body)
result = total
"""


def test_6c_sibling_roots_get_independent_scopes() -> None:
    # Issue 006 6c (root-scope wrap): two sibling root instances that
    # both bind `total` at their top level must emit as independent
    # variables — hygiene sees each root as a distinct Astichi scope
    # thanks to the `astichi_hole` / `@astichi_insert` wrap added by
    # `build_merge`, so `rename_scope_collisions` renames one set.
    # Each root's nested `astichi_import(total)` threads to *its own*
    # root scope (not to the shared module scope), so the Step shells
    # inside Root stay wired to Root's `total` and likewise for ARoot.
    builder = astichi.build()
    builder.add.Root(astichi.compile(_ACCUM_ROOT_SRC))
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.add.Step2(astichi.compile(_accum_step_src(2)))
    builder.add.Step3(astichi.compile(_accum_step_src(3)))
    builder.Root.body.add.Step1(order=0)
    builder.assign.Step1.total.to().Root.total
    builder.Root.body.add.Step2(order=1)
    builder.assign.Step2.total.to().Root.total
    builder.Root.body.add.Step3(order=2)
    builder.assign.Step3.total.to().Root.total

    builder.add.ARoot(astichi.compile(_ACCUM_ROOT_SRC))
    builder.add.AStep1(astichi.compile(_accum_step_src(1)))
    builder.add.AStep2(astichi.compile(_accum_step_src(2)))
    builder.add.AStep3(astichi.compile(_accum_step_src(3)))
    builder.ARoot.body.add.AStep1(order=0)
    builder.assign.AStep1.total.to().ARoot.total
    builder.ARoot.body.add.AStep2(order=1)
    builder.assign.AStep2.total.to().ARoot.total
    builder.ARoot.body.add.AStep3(order=2)
    builder.assign.AStep3.total.to().ARoot.total

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)

    # The root-scope hole+shell wrap must flatten out of the emitted
    # program — `__astichi_root__*__` anchors are internal scaffolding.
    assert "__astichi_root__" not in source
    assert "astichi_insert" not in source
    assert "astichi_hole" not in source
    # Exactly one scope keeps the un-suffixed `total` / `result` names;
    # the other sibling scope gets `__astichi_scoped_*` mangled forms.
    assert "total__astichi_scoped_" in source
    assert "result__astichi_scoped_" in source

    namespace = _exec_emitted(materialized)
    # Two separate accumulators: Root sums 1+2+3 = 6 under `result`;
    # ARoot does the same under the mangled `result__astichi_scoped_*`.
    all_values = [
        value for key, value in namespace.items() if key.startswith("result")
    ]
    assert sorted(all_values) == [6, 6]


def _accum_step_src(value: int) -> str:
    return (
        "astichi_import(total)\n"
        "\n"
        f"total = total + {value}\n"
    )


def _exec_emitted(composable) -> dict[str, object]:
    source = composable.emit(provenance=False)
    namespace: dict[str, object] = {}
    exec(compile(source, "<test>", "exec"), namespace)  # noqa: S102
    return namespace


def test_6c_import_threading_unifies_total_across_shells() -> None:
    # Issue 006 6c: three StepN shells each declare
    # `astichi_import(total)`. With the hygiene fix classifying
    # Store/Load of `total` to the outer Astichi scope, the shells'
    # Stores collapse onto Root's `total` instead of renaming to
    # shell-local `total__astichi_scoped_N`.
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.add.Step2(astichi.compile(_accum_step_src(2)))
    builder.add.Step3(astichi.compile(_accum_step_src(3)))
    builder.Root.body.add.Step1(order=0, arg_names={"total": "total"})
    builder.Root.body.add.Step2(order=1, arg_names={"total": "total"})
    builder.Root.body.add.Step3(order=2, arg_names={"total": "total"})

    materialized = builder.build().materialize()
    namespace = _exec_emitted(materialized)

    assert namespace["total"] == 6
    assert namespace["result"] == 6


def test_6c_materialize_strips_astichi_import_statements() -> None:
    # Issue 006 6c: residual `astichi_import(name)` Expr statements
    # must not appear in the emitted source — the residual-marker
    # stripper deletes them after port extraction and hygiene.
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.Root.body.add.Step1(order=0, arg_names={"total": "total"})

    source = builder.build().materialize().emit(provenance=False)

    assert "astichi_import" not in source
    assert "astichi_pass" not in source


def test_6c_non_identity_arg_names_renames_import_to_outer_target() -> None:
    # Issue 006 6c: `arg_names={"total": "accumulator"}` rewrites every
    # `total` Name/arg inside the declaring shell body to `accumulator`
    # before hygiene runs, threading the Stores onto an outer
    # `accumulator` binding.
    root_src = """
accumulator = 0
astichi_hole(body)
result = accumulator
"""
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(root_src)
    )
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.add.Step2(astichi.compile(_accum_step_src(2)))
    builder.Root.body.add.Step1(
        order=0, arg_names={"total": "accumulator"}
    )
    builder.Root.body.add.Step2(
        order=1, arg_names={"total": "accumulator"}
    )

    materialized = builder.build().materialize()
    source = materialized.emit(provenance=False)
    assert "total" not in source
    namespace = _exec_emitted(materialized)
    assert namespace["accumulator"] == 3
    assert namespace["result"] == 3


def test_6c_default_scope_import_threads_without_explicit_arg_names() -> None:
    # Issue 006 6c: without any explicit wiring the import defaults
    # to "same name in outer scope". The shell body's Store/Load of
    # `total` still threads onto Root's `total`.
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.Root.body.add.Step1(order=0)

    namespace = _exec_emitted(builder.build().materialize())
    assert namespace["total"] == 1
    assert namespace["result"] == 1


def test_6c_builder_arg_names_rejects_unknown_import_slot() -> None:
    # Issue 006 6c: the target-adder arg_names map is validated by
    # `BasicComposable.bind_identifier`, which now accepts both
    # `__astichi_arg__`- and `astichi_import`-sourced IDENTIFIER
    # demand ports. An unknown slot still raises.
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.add.Step1(astichi.compile(_accum_step_src(1)))

    with pytest.raises(
        ValueError,
        match=r"no __astichi_arg__ / astichi_import slot named `missing`",
    ):
        builder.Root.body.add.Step1(order=0, arg_names={"missing": "total"})


def test_6c_compile_arg_names_accepts_import_sourced_demand() -> None:
    # Issue 006 6c: `astichi.compile(..., arg_names={"total": "total"})`
    # is valid for a piece whose only IDENTIFIER demand comes from an
    # `astichi_import` declaration (no `__astichi_arg__` suffix
    # anywhere).
    compiled = astichi.compile(
        _accum_step_src(5),
        arg_names={"total": "total"},
    )
    assert compiled.arg_bindings == (("total", "total"),)


# ---------------------------------------------------------------------------
# Issue 006 6c (assign surface):
# `builder.assign.<Src>.<inner>.to().<Dst>.<outer>`
# ---------------------------------------------------------------------------


def test_6c_assign_surface_threads_import_end_to_end() -> None:
    # Issue 006 6c assign surface: declaring the binding via
    # `builder.assign.Step1.total.to().Root.total` is equivalent to
    # passing `arg_names={"total": "total"}` at contribution time.
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.add.Step2(astichi.compile(_accum_step_src(2)))
    builder.add.Step3(astichi.compile(_accum_step_src(3)))
    builder.Root.body.add.Step1(order=0)
    builder.Root.body.add.Step2(order=1)
    builder.Root.body.add.Step3(order=2)
    builder.assign.Step1.total.to().Root.total
    builder.assign.Step2.total.to().Root.total
    builder.assign.Step3.total.to().Root.total

    namespace = _exec_emitted(builder.build().materialize())
    assert namespace["result"] == 6


def test_6c_assign_surface_allows_deferred_target_instance() -> None:
    # Issue 006 6c: the target instance named in the assign chain can
    # be registered *after* the assign is declared. Validation is
    # deferred to `build_merge` so wirings can point at pieces that do
    # not exist yet.
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(7)))
    builder.assign.Step1.total.to().Root.total
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.Root.body.add.Step1(order=0)

    namespace = _exec_emitted(builder.build().materialize())
    assert namespace["result"] == 7


def test_6c_assign_surface_to_non_edge_target_instance() -> None:
    # Issue 006 6c: the target in `builder.assign` is *not* required to
    # be the edge target. Step1 is spliced into Root.body but its
    # `total` import is wired to `Init.total` — a different sibling
    # instance that owns the initialisation. The assign surface does
    # not affect merge order (multi-root merge is alphabetical), so we
    # name the supplier `Init` (< "Root" < "Step1") to keep the
    # emitted sequence semantically correct.
    builder = astichi.build()
    init_src = """
total = 10
astichi_keep(total)
"""
    builder.add.Init(astichi.compile(init_src))
    root_src = """
astichi_keep(total)
astichi_hole(body)
result = total
"""
    builder.add.Root(
        astichi.compile(root_src, keep_names=["total", "result"])
    )
    builder.add.Step1(astichi.compile(_accum_step_src(4)))
    builder.Root.body.add.Step1(order=0)
    builder.assign.Step1.total.to().Init.total

    namespace = _exec_emitted(builder.build().materialize())
    assert namespace["total"] == 14
    assert namespace["result"] == 14


def test_6c_assign_surface_is_idempotent_for_exact_duplicate_declarations() -> None:
    # Issue 006 6c: restating the exact same assignment is a no-op —
    # the guard in `BuilderGraph.add_assign` ignores an identical
    # second record rather than raising. This matters because the
    # terminal `__getattr__` has an unavoidable side-effect surface.
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.assign.Step1.total.to().Root.total
    builder.assign.Step1.total.to().Root.total  # idempotent

    assert len(builder.graph.assigns) == 1


def test_6c_assign_surface_rejects_conflicting_rebind_of_same_demand() -> None:
    # Issue 006 6c: the same `(source_instance, inner_name)` pair can
    # only bind to one supplier. Declaring a second, different
    # supplier is a hard error at the `builder.assign` call site.
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.assign.Step1.total.to().Root.total

    with pytest.raises(ValueError, match=r"conflicting assign for `Step1\.total`"):
        builder.assign.Step1.total.to().Other.accumulator


def test_6c_assign_surface_rejects_unknown_source_at_build() -> None:
    # Issue 006 6c: validation is deferred, but `build_merge` rejects
    # assigns that reference an unknown source instance.
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.assign.Missing.total.to().Root.total

    with pytest.raises(ValueError, match=r"unknown source instance `Missing`"):
        builder.build()


def test_6c_assign_surface_rejects_unknown_target_at_build() -> None:
    # Issue 006 6c: likewise, a missing target instance surfaces as a
    # build-time error that names the offending `(source, inner)`.
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.assign.Step1.total.to().Missing.total

    with pytest.raises(
        ValueError,
        match=r"unknown target instance `Missing` \(from Step1\.total\)",
    ):
        builder.build()


def test_6c_assign_surface_rejects_unknown_inner_demand_slot_at_build() -> None:
    # Issue 006 6c: when the referenced inner name is not a demand
    # port on the source instance, `bind_identifier` rejects at build
    # time with the same error as the `arg_names=` surface.
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.assign.Step1.nonexistent.to().Root.total

    with pytest.raises(
        ValueError,
        match=(
            r"no __astichi_arg__ / astichi_import slot named "
            r"`nonexistent`"
        ),
    ):
        builder.build()


def test_6c_assign_surface_connects_dangling_pass_across_build_stages() -> None:
    # Issue 006 6c assign surface: multi-stage composition. Stage 1
    # builds a composable whose `astichi_pass(counter)` declaration is
    # dangling — no edge in stage 1 consumes it, so the supply
    # survives on the merged composable as a port. Stage 2 re-uses
    # that composable as an instance and adds a sibling reader that
    # declares `astichi_import(counter)`; `builder.assign` wires them
    # fully-qualified across the stage boundary.
    producer_src = """
astichi_pass(counter)

counter = 42
"""
    stage1 = astichi.build()
    stage1.add.Producer(astichi.compile(producer_src))
    stage1_composable = stage1.build()

    # The merged stage-1 composable still advertises `counter` as an
    # IDENTIFIER supply port with source_tag="pass" — the marker and
    # the port survive through `build_merge` because nothing in stage
    # 1 consumed them.
    counter_supply = [
        port for port in stage1_composable.supply_ports if port.name == "counter"
    ]
    assert counter_supply, (
        "stage 1 should advertise the dangling `counter` pass as a "
        "supply port on the merged composable"
    )
    assert "pass" in counter_supply[0].sources

    reader_src = """
astichi_import(counter)

result = counter * 2
"""
    stage2 = astichi.build()
    stage2.add.Producer(stage1_composable)
    stage2.add.Reader(astichi.compile(reader_src, keep_names=["result"]))
    # Connect the Reader's dangling import demand in stage 2 to the
    # Producer's dangling pass supply from stage 1. The producer
    # composable does not have to be re-inspected by the user: the
    # fully-qualified assign names the supplier by (instance, name).
    stage2.assign.Reader.counter.to().Producer.counter

    namespace = _exec_emitted(stage2.build().materialize())
    assert namespace["counter"] == 42
    assert namespace["result"] == 84
