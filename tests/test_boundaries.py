"""Tests for the Astichi boundary markers (issue 006 6a + 6b)."""

from __future__ import annotations

import ast

import pytest

import astichi
from astichi.builder.graph import AssignBinding
from astichi.lowering import MARKERS_BY_NAME
from astichi.model.ports import IDENTIFIER


def test_import_and_pass_markers_are_registered() -> None:
    # Issue 006: `astichi_import` and `astichi_pass` are recognised
    # marker surfaces and both carry a name-bearing first argument.
    assert "astichi_import" in MARKERS_BY_NAME
    assert "astichi_pass" in MARKERS_BY_NAME
    assert MARKERS_BY_NAME["astichi_import"].is_name_bearing() is True
    assert MARKERS_BY_NAME["astichi_pass"].is_name_bearing() is True


def test_compile_recognizes_module_level_boundary_markers() -> None:
    compiled = astichi.compile(
        """
astichi_import(outer_name)
value = astichi_pass(inner_name)

result = outer_name + value
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
    # Issue 006: both `astichi_import(name)` and value-form
    # `astichi_pass(name)` surface as IDENTIFIER demand ports.
    compiled = astichi.compile(
        """
astichi_import(dep)
result = astichi_pass(seed)

value = dep + result
"""
    )

    dep_port = next(
        port for port in compiled.demand_ports if port.name == "dep"
    )
    assert dep_port.shape is IDENTIFIER
    assert dep_port.placement == "identifier"
    assert "import" in dep_port.sources

    seed_port = next(
        port for port in compiled.demand_ports if port.name == "seed"
    )
    assert seed_port.shape is IDENTIFIER
    assert seed_port.placement == "identifier"
    assert "pass" in seed_port.sources


def test_placement_accepts_top_prefix_import_at_module_and_shell_scopes() -> None:
    astichi.compile(
        """
astichi_import(outer)
top_result = outer

@astichi_insert(target)
def shell_block():
    astichi_import(shared)
    nested_out = shared + 1

result = top_result
"""
    )


def test_placement_rejects_boundary_after_real_statement_in_module() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(\.\.\.\) at line \d+ in module body: boundary markers must form the top-of-body prefix",
    ):
        astichi.compile(
            """
x = 1
astichi_import(late)
"""
        )


def test_placement_accepts_boundary_inside_non_shell_def() -> None:
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
        match=r"astichi_import\(\.\.\.\) at line \d+ in shell 'block' body",
    ):
        astichi.compile(
            """
@astichi_insert(target)
def block():
    astichi_import(ok_prefix)
    ok_prefix
    astichi_import(late_in_shell)
"""
        )


def test_placement_allows_multiple_prefix_import_statements() -> None:
    astichi.compile(
        """
astichi_import(a)
astichi_import(b)

c = a
d = b
"""
    )


def test_placement_rejects_bare_astichi_pass_statement_with_import_hint() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_pass\(\.\.\.\).*value-form only.*astichi_import",
    ):
        astichi.compile(
            """
astichi_pass(counter)
"""
        )


def test_placement_rejects_bare_astichi_pass_sentinel_statement_with_import_hint() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_pass\(\.\.\.\).*value-form only.*astichi_import",
    ):
        astichi.compile(
            """
astichi_pass(counter).astichi_v
"""
        )


def test_placement_accepts_astichi_pass_in_assignment_rhs() -> None:
    astichi.compile(
        """
result = astichi_pass(bound_name)
"""
    )


def test_placement_accepts_astichi_pass_as_module_level_walrus_rhs() -> None:
    # ``astichi_pass`` may appear as the RHS of a top-level walrus so the
    # walrus target and pass-through name are distinct bindings.
    astichi.compile(
        """
astichi_export(out)
(result := astichi_pass(inner))
"""
    )


def test_placement_accepts_astichi_import_as_walrus_rhs() -> None:
    astichi.compile(
        """
(x := astichi_import(y))
"""
    )


def test_placement_accepts_astichi_pass_walrus_inside_compound_statement() -> None:
    astichi.compile(
        """
if True:
    (x := astichi_pass(y))
"""
    )


def test_placement_rejects_bare_astichi_ref_statement() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_ref\(\.\.\.\) at line \d+ is value-form only",
    ):
        astichi.compile("astichi_ref('pkg.mod')\n")


def test_placement_rejects_bare_astichi_ref_sentinel_statement() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_ref\(\.\.\.\) at line \d+ is value-form only",
    ):
        astichi.compile("astichi_ref('pkg.mod').astichi_v\n")


def test_pass_sentinel_assign_lowers_to_identifier_store() -> None:
    rendered = ast.unparse(
        astichi.compile("astichi_pass(counter).astichi_v = 42\n")
        .materialize()
        .tree
    )
    assert rendered.strip() == "counter = 42"


def test_pass_sentinel_chain_is_transparent_once() -> None:
    rendered = ast.unparse(
        astichi.compile("value = astichi_pass(obj)._.field\n")
        .materialize()
        .tree
    )
    assert rendered.strip() == "value = obj.field"


def test_pass_sentinel_method_call_is_transparent_once() -> None:
    namespace = _exec_emitted(
        astichi.compile(
            """
shared_trace = []
astichi_pass(shared_trace)._.append("leaf")
"""
        ).materialize()
    )
    assert namespace["shared_trace"] == ["leaf"]


def test_pass_sentinel_strips_once_so_real_underscore_field_remains() -> None:
    rendered = ast.unparse(
        astichi.compile("value = astichi_pass(obj)._._\n")
        .materialize()
        .tree
    )
    assert rendered.strip() == "value = obj._"


def test_nested_pass_requires_outer_bind_or_explicit_wiring() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
events = []
astichi_hole(body)
result = events
"""
        )
    )
    builder.add.Step(
        astichi.compile('astichi_pass(events).append("leaf")\n')
    )
    builder.Root.body.add.Step(order=0)

    with pytest.raises(
        ValueError,
        match=r"unresolved boundary identifier demands: astichi_pass\(events\)",
    ):
        builder.build().materialize()


def test_nested_pass_outer_bind_threads_same_name_explicitly() -> None:
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(
            """
events = []
astichi_hole(body)
result = events
"""
        )
    )
    builder.add.Step(
        astichi.compile(
            'astichi_pass(events, outer_bind=True).append("leaf")\n'
        )
    )
    builder.Root.body.add.Step(order=0)

    namespace = _exec_emitted(builder.build().materialize())
    assert namespace["result"] == ["leaf"]


# ---------------------------------------------------------------------------
# 6b: hygiene pinning + interaction matrix
# ---------------------------------------------------------------------------


def test_import_and_pass_do_not_clone_implied_demands() -> None:
    compiled = astichi.compile(
        """
astichi_import(dep)
value = astichi_pass(seed)
out = dep + value
"""
    )

    dep_sources = {
        port.sources
        for port in compiled.demand_ports
        if port.name == "dep"
    }
    assert dep_sources == {frozenset({"import"})}
    seed_sources = {
        port.sources
        for port in compiled.demand_ports
        if port.name == "seed"
    }
    assert seed_sources == {frozenset({"pass"})}


def test_interaction_matrix_rejects_import_and_pass_on_same_name() -> None:
    with pytest.raises(
        ValueError,
        match=r"astichi_import\(x\).*conflicts with astichi_pass\(x\)",
    ):
        astichi.compile(
            """
astichi_import(x)
value = astichi_pass(x)
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


def test_interaction_matrix_allows_pass_alongside_non_conflicting_markers() -> None:
    astichi.compile(
        """
value = astichi_pass(inbound)

class handler__astichi_keep__:
    pass


def knob__astichi_arg__():
    return 0

shared = 42
astichi_export(shared)
"""
    )


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
        match=r"no __astichi_arg__ / astichi_import / astichi_pass slot named `missing`",
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

    with pytest.raises(ValueError, match=r"build: conflicting assign for `Step1\.total`"):
        builder.assign.Step1.total.to().Other.accumulator


def test_6c_assign_surface_rejects_unknown_source_at_build() -> None:
    # Issue 006 6c: validation is deferred, but `build_merge` rejects
    # assigns that reference an unknown source instance.
    builder = astichi.build()
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    builder.assign.Missing.total.to().Root.total

    with pytest.raises(
        ValueError, match=r"materialize: builder.assign refers to unknown source instance `Missing`"
    ):
        builder.build()


def test_6c_assign_surface_rejects_unknown_target_at_build() -> None:
    # Issue 006 6c: likewise, a missing target instance surfaces as a
    # build-time error that names the offending `(source, inner)`.
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.assign.Step1.total.to().Missing.total

    with pytest.raises(
        ValueError,
        match=r"materialize: builder.assign refers to unknown target instance `Missing` \(from Step1\.total\)",
    ):
        builder.build()


def test_6c_assign_surface_rejects_unknown_inner_demand_slot_at_build() -> None:
    # Issue 006 6c: when the referenced inner name is not a demand
    # port on a registered source instance, the fluent surface rejects
    # immediately with the same error as the `arg_names=` surface.
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.add.Root(
        astichi.compile(_ACCUM_ROOT_SRC)
    )
    with pytest.raises(
        ValueError,
        match=(
            r"build: no __astichi_arg__ / astichi_import / astichi_pass slot named "
            r"`nonexistent`"
        ),
    ):
        builder.assign.Step1.nonexistent.to().Root.total


def test_6c_assign_surface_rejects_index_at_end_of_source_path() -> None:
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(1)))

    with pytest.raises(
        ValueError,
        match=r"assign identifier paths may not end with index segments",
    ):
        builder.assign.Step1.total[0].to().Root.total


def test_6c_assign_surface_rejects_index_after_final_target_name() -> None:
    builder = astichi.build()
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.add.Root(astichi.compile(_ACCUM_ROOT_SRC))

    with pytest.raises(
        ValueError,
        match=(
            r"assign target identifier paths may not continue with index segments "
            r"after final outer name `Root\.total`"
        ),
    ):
        builder.assign.Step1.total.to().Root.total[0]


def test_6c_assign_surface_raw_build_rejects_unknown_deep_source_path() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile("astichi_import(total)\nvalue = total + 1\n"))
    stage1.Root.body.add.Inner()
    built = stage1.build()

    builder = astichi.build()
    builder.add.Pipeline(built)
    builder.add.Root(astichi.compile(_ACCUM_ROOT_SRC))
    builder.graph.add_assign(
        AssignBinding(
            source_instance="Pipeline",
            inner_name="total",
            source_ref_path=("Missing",),
            target_instance="Root",
            outer_name="total",
        )
    )

    with pytest.raises(
        ValueError,
        match=r"unknown assign source path `Pipeline\.Missing`",
    ):
        builder.build()


def test_6c_assign_surface_raw_build_rejects_unknown_deep_target_path() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile("total = 10\n"))
    stage1.Root.body.add.Inner()
    built = stage1.build()

    builder = astichi.build()
    builder.add.Pipeline(built)
    builder.add.Step1(astichi.compile(_accum_step_src(1)))
    builder.graph.add_assign(
        AssignBinding(
            source_instance="Step1",
            inner_name="total",
            target_instance="Pipeline",
            outer_name="total",
            target_ref_path=("Missing",),
        )
    )

    with pytest.raises(
        ValueError,
        match=r"unknown assign target path `Pipeline\.Missing`",
    ):
        builder.build()


def test_6c_assign_surface_connects_exported_supplier_across_build_stages() -> None:
    # Issue 006 assign surface: multi-stage composition. Stage 1 builds
    # a composable that explicitly exports `counter`; stage 2 re-uses
    # that composable as an instance and adds a sibling reader that
    # declares `astichi_import(counter)`. `builder.assign` wires them
    # fully-qualified across the stage boundary.
    producer_src = """
astichi_keep(counter)
counter = 42
astichi_export(counter)
"""
    stage1 = astichi.build()
    stage1.add.Producer(astichi.compile(producer_src))
    stage1_composable = stage1.build()

    # The merged stage-1 composable still advertises `counter` as a
    # supply port with source_tag="export"` — the marker and the port
    # survive through `build_merge` because nothing in stage 1 consumed
    # them.
    counter_supply = [
        port for port in stage1_composable.supply_ports if port.name == "counter"
    ]
    assert counter_supply, (
        "stage 1 should advertise the exported `counter` as a "
        "supply port on the merged composable"
    )
    assert "export" in counter_supply[0].sources

    reader_src = """
astichi_import(counter)

result = counter * 2
"""
    stage2 = astichi.build()
    stage2.add.Producer(stage1_composable)
    stage2.add.Reader(astichi.compile(reader_src, keep_names=["result"]))
    # Connect the Reader's dangling import demand in stage 2 to the
    # Producer's exported supply from stage 1. The producer
    # composable does not have to be re-inspected by the user: the
    # fully-qualified assign names the supplier by (instance, name).
    stage2.assign.Reader.counter.to().Producer.counter

    namespace = _exec_emitted(stage2.build().materialize())
    assert namespace["counter"] == 42
    assert namespace["result"] == 84


def test_6c_assign_surface_deep_source_path_across_stage_boundary() -> None:
    inner_src = """
astichi_import(total)

result = total + 1
"""
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Inner(astichi.compile(inner_src, keep_names=["result"]))
    stage1.Root.body.add.Inner()
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Init(astichi.compile("total = 10\nastichi_keep(total)\n"))
    stage2.add.Pipeline(built)
    stage2.assign.Pipeline.Inner.total.to().Init.total

    namespace = _exec_emitted(stage2.build().materialize())
    assert namespace["total"] == 10
    assert namespace["result"] == 11


def test_6c_assign_surface_deep_target_path_selects_nested_supplier() -> None:
    stage1 = astichi.build()
    stage1.add.Root(astichi.compile("astichi_hole(body)\n"))
    stage1.add.Left(astichi.compile("total = 10\n"))
    stage1.add.Right(astichi.compile("astichi_keep(total)\ntotal = 20\n"))
    stage1.Root.body.add.Left(order=0)
    stage1.Root.body.add.Right(order=1)
    built = stage1.build()

    stage2 = astichi.build()
    stage2.add.Pipeline(built)
    stage2.add.Step(
        astichi.compile(
            "astichi_import(total)\nstep_result = total + 1\n",
            keep_names=["step_result"],
        )
    )
    stage2.Pipeline.body.add.Step(order=2)
    stage2.assign.Step.total.to().Pipeline.Right.total

    namespace = _exec_emitted(stage2.build().materialize())
    values = [
        value for key, value in namespace.items() if key.startswith("step_result")
    ]
    assert values == [21]
