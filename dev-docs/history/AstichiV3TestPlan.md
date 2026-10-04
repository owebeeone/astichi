# Astichi V3 test plan

This document defines the next test expansion for Astichi composition.

The immediate goal is not "more tests" in the abstract. The goal is to
strengthen confidence in:

- deep nesting
- staged builds (`build()` output reused as later-stage input)
- order stability across nested and staged composition
- late parameter/value binding
- explicit cross-scope wiring
- keep/arg resolution and leak prevention

This plan assumes the current implemented surface in `src/` and the green test
suite as of `2026-04-19`.

**Related design:** `AstichiSingleSourceSummary.md` §3.2 (build surface, ref-path
`assign`, deferred **aliases**). Optional detail: `BuilderIdentityAndAliasesDesign.md`.
When alias support lands, extend spine tests here for stable named references
across stages.

## 1. Problem statement

Current testing is reasonably good at single-stage merge behavior and at
individual feature slices, but still light on:

- recursive composition where a stage-built composable becomes a later-stage
  input
- exact ordering behavior when nesting depth and stage depth both increase
- delayed binding of values or identifiers after an earlier `build()`
- reusing the same stage-built composable multiple times with different
  per-instance bindings
- mixed-surface tests that combine holes, identifier demands, keeps,
  import/pass/export, and unroll in one scenario

That is the gap this plan closes.

## 2. Testing philosophy

Do not attempt a literal full Cartesian product of every operation against every
other operation. The surface is already too large, and the resulting tests would
be unreadable and hard to debug.

Use two layers instead:

1. a small set of **spine tests**
   - deep, realistic, story-shaped integration tests
   - each should exercise several surfaces together
   - these are the high-value staged-composition tests
2. a focused set of **matrix tests**
   - short, parameterized, axis-driven
   - each isolates one semantic dimension

This yields better coverage than either:

- one mega-test that tries to prove everything
- a giant unstructured pile of tiny tests with no model behind them

### 2.1 Test-writing constraints for V3

The V3 staged-composition suite should follow these rules.

- do not use `keep_names=` during the build process in new staged tests
- do not use `arg_names=` as the primary happy-path variable-binding mechanism
  in new staged tests
- variable-binding scenarios in staged tests should be expressed through the
  marker surface:
  - consumers use `astichi_import(...)`
  - value-form scoped reads use `astichi_pass(...)`
  - outward publication uses `astichi_export(...)`
- keep behavior, when tested here, should use marker keep surfaces rather than
  build-time `keep_names=...`

Lower-level suites may continue to cover `arg_names=` and `keep_names=` as API
surfaces. The V3 plan is intentionally focused on staged composition via the
snippet/marker model.

## 3. Notation

Use the following notation in this plan and in future discussion.

### 3.1 Stage and composable notation

- `S_n`: build stage `n`
- `G_n`: builder graph used in stage `n`
- `B_n`: result of `G_n.build(...)`; a composable produced by stage `n`
- `M_n`: `B_n.materialize()`
- `C_n`: leaf composable `n`
- `R_n`: root-like leaf composable used as a stage entry point

### 3.2 Demand / supply notation

- `H(name)`: named hole
- `H(name[i])`, `H(name[i,j])`: indexed hole after unroll
- `X(name)`: external literal demand from `astichi_bind_external(name)`
- `A(name)`: identifier demand from `name__astichi_arg__`
- `K(name)`: keep pin from `astichi_keep(name)` or `name__astichi_keep__`
- `I(name)`: boundary import from `astichi_import(name)`
- `P(name)`: value-form scoped read from `astichi_pass(name)`
- `E(name)`: exported binding from `astichi_export(name)`

### 3.3 Builder notation

- `wire T.H <- S @o=k`: additive edge from source instance `S` into target hole
  `H` on target instance `T`, with `order=k`
- `assign S.inner => T.outer`: builder-level identifier wiring
- descendant/ref paths stay in the same fluent form as the public builder API:
  - `T` may be just a root instance (`Root`)
  - or a descendant path (`Pipeline.Root.Parse`, `Pipeline.Root.Parse.rows[1,2].Normalize`)
  - examples:
    - `wire Pipeline.Root.Parse.body <- Step @o=0`
    - `assign Step.total => Pipeline.Root.Right.total`
- emitted shell metadata for the same addressed descendant uses
  `@astichi_insert(..., ref=Pipeline.Root.Parse[1, 2].Normalize)`
- `bind X {name=value}`: apply `.bind(...)` to a composable
- `arg X {inner->outer}`: apply identifier binding (`arg_names=` /
  `.bind_identifier(...)`)
- `keep X {name}`: apply keep pin (`keep_names=` / `.with_keep_names(...)`)

### 3.4 Example sentence

```text
S1:
  wire Root.body <- C1 @o=0
  wire Root.body <- C2 @o=1
  => B1

S2:
  wire Outer.body <- B1 @o=1
  wire Outer.body <- C3 @o=0
  => B2
```

This means:

- stage 1 builds `B1` from `Root + C1 + C2`
- stage 2 reuses `B1` as a source instance under `Outer`
- final order is determined by the stage-2 outer order plus stage-1 preserved
  inner order

## 4. Complete operation catalog

This is the complete current operation catalog we care about for staged
composition tests.

### 4.1 Pre-stage composable transforms

- `astichi.compile(...)`
- `composable.bind(...)`
- `composable.bind_identifier(...)`
- `composable.with_keep_names(...)`

### 4.2 Stage-local graph operations

- `builder.add.<Name>(piece, *, arg_names=..., keep_names=...)`
- `builder.<Target>.<hole>.add.<Source>(order=..., arg_names=..., keep_names=...)`
- `builder.<Target>.<hole>[i]...add.<Source>(...)`
- `builder.<Target>.<descendant>...[i]...<hole>.add.<Source>(...)`
- `builder.assign.<Src>.<inner>.to().<Dst>.<outer>`
- `builder.assign.<Src>.<descendant>...<inner>.to().<Dst>.<descendant>...<outer>`
- `builder.build(unroll="auto" | True | False)`

### 4.3 Between-stage operations

- use `B_n` as an input piece in `S_(n+1)`
- bind `B_n` later via `.bind(...)`
- bind identifiers on `B_n` later via `.bind_identifier(...)`
- add `B_n` multiple times in the same later stage with distinct
  `arg_names=` / `keep_names=...`

### 4.4 Terminal operations

- `materialize()`
- `emit(provenance=False)`
- `emit(provenance=True)` + `verify_round_trip(...)`
- `exec(...)` on emitted source where runtime behavior is part of the contract

## 5. Coverage model

The suite should cover these axes.

| Axis | Representative values |
|------|------------------------|
| Stage depth | `S1` only, `S1 -> S2`, `S1 -> S2 -> S3` |
| Structural depth | flat, parent/child, grandchild nesting |
| Demand kind | block hole, plain call hole, `*` call hole, `**` call hole, external literal, identifier import/arg |
| Supply kind | plain inserted piece, `astichi_funcargs(...)`, `astichi_pass`, `astichi_export`, outer local binding |
| Wiring surface | compile-time `arg_names`, add-time `arg_names`, edge-time `arg_names`, `builder.assign` |
| Rename mode | identity (`x -> x`), non-identity (`x -> y`) |
| Keep surface | marker keep, suffix keep, `keep_names=` |
| Ordering mode | increasing order, decreasing order, equal-order stable tie |
| Ref-path shape | root-only, one-hop descendant, multi-hop descendant, descendant + index |
| Ref-path surface | additive target path, assign source path, assign target path, emitted `ref=` shell metadata |
| Registration timing | target/source already registered, forward-declared root, forward-declared deep target reject |
| Unroll timing | literal domain now, bind-fed domain later, auto-unroll, forced unroll |
| Failure phase | build-time reject, materialize-time reject, runtime contract |

Not every axis needs to be combined with every other axis. Each axis must,
however, be exercised in at least one spine test and at least one focused matrix
test where the behavior is central.

## 6. What is already covered

Important current coverage already exists.

- sibling-root scope independence:
  `tests/test_boundaries.py::test_6c_sibling_roots_get_independent_scopes`
- same-stage import threading via `arg_names=`:
  `tests/test_boundaries.py::test_6c_import_threading_unifies_total_across_shells`
- `builder.assign` end-to-end and delayed target registration:
  `tests/test_boundaries.py::test_6c_assign_surface_*`
- stage-built dangling `pass` consumed in a later stage:
  `tests/test_boundaries.py::test_6c_assign_surface_connects_dangling_pass_across_build_stages`
- unroll integration and bind-fed domains in a single stage:
  `tests/test_build_merge.py`
- add-time `arg_names=` / `keep_names=`:
  `tests/test_builder_handles.py`

V3 should build on those tests, not replace them.

## 6.1 Ref-path resolution contract to lock before staged spines

The recent descendant-path work tightened the contract that V3 tests must
assume.

- non-root descendant paths must resolve to exactly one preserved shell
- unknown non-root descendant paths reject
- ambiguous repeated-use descendant paths reject
- duplicate preserved non-root full `ref=` paths on a reused built composable
  reject at registration time
- eager validation is intentionally strongest for non-empty descendant paths
- root-only path behavior remains slightly looser because of the preserved
  root-wrap shell; do not assume root-path validation fires at exactly the same
  phase as descendant-path validation

This means V3 should not spend its staged spines re-proving every basic
path-rejection case. Lock those semantics in a small focused matrix first, then
use the staged tests for stage-boundary behavior only.

## 7. High-priority gaps

The next tests should specifically add coverage for the following gaps.

### 7.1 Deep nested order across stages

We do not yet have one strong test that proves:

- inner order is preserved when a built composable is reused later
- outer order still dominates at the later stage
- equal-order ties remain stable under nesting

### 7.2 Late binding of stage-built composables

We need direct tests for:

- `B_n.bind(...)` in a later stage, before the next build
- `B_n.bind_identifier(...)` in a later stage
- using the same `B_n` multiple times with different later-stage bindings

This is the highest-value place to look for the suspected API bug.

### 7.3 Mixed-surface staged tests

Current tests cover many features individually, but not enough scenarios where
the same pipeline combines:

- block stitching
- descendant/ref-path addressing
- identifier wiring
- keeps
- pass/export supply
- delayed unroll

### 7.4 Ref-path semantics vs metadata surface

We need explicit tests that separate:

- the **semantic** guarantee: descendant add / assign resolves against the
  intended nested shell
- the **metadata** guarantee: emitted block shells carry the same path in the
  public fluent `ref=...` syntax

Both matter. The semantic tests catch incorrect merge/materialize behavior; the
metadata tests catch drift between the public source form and the runtime's
internal decomposed representation.

Also add one small focused rejection matrix before the staged spines:

- unknown deep additive target path rejects
- unknown deep assign source/target path rejects
- ambiguous repeated descendant path rejects
- duplicate non-root preserved `ref=` path rejects on reuse
- invalid trailing index rejects

### 7.5 Export as a staged supplier

`pass/import` is better covered than `export` as a later-stage supplier. We need
tests that prove stage-built exports survive and are consumable in the next
stage.

### 7.6 Registration-order limits on deep assign

Current deep target-side `assign` discovery depends on the target instance
already being registered so descendant hops are knowable from its shell refs.
The plan should cover both:

- supported case: deep target path on an already-registered target instance
- current rejection case: deep target path on a forward-declared target instance

This is not a vague future-support bucket. The current deep target-side
forward-declared case should be written as an explicit rejection test unless the
implementation changes.

### 7.7 Expression and variadic surfaces under staging

Most staged discussion defaults to block holes. V3 should explicitly cover:

- `astichi_funcargs(...)` into plain call holes
- `*astichi_hole(...)`
- `**astichi_hole(...)`

with stage-built sources, not just leaf sources.

## 8. Proposed spine tests

These are the first tests to write.

### 8.1 `test_v3_spine_multistage_deep_order_trace`

Purpose:

- prove exact order preservation under nested, staged composition

Shape:

- `C1`, `C2`, `C3`, `C4` are trace-appending leaves
- `R1` is a shell root with `H(body)` and pre/post trace markers
- `S1` builds `B1` from `R1 + C1 + C2`
- `S2` builds `B2` from another shell + `B1 + C3 + C4`
- use one equal-order tie and one outer-stage order inversion

Assertions:

- exact final trace list
- inner tie remains first-added
- stage-2 outer order dominates stage-1 block placement
- no markers survive materialized emit

Implementation note:

- use a mutable `trace` list at runtime, not source substring matching

### 8.2 `test_v3_spine_late_bind_external_then_unroll_in_later_stage`

Purpose:

- prove that a stage-built composable can retain an unresolved external domain
  and be bound only in a later stage before indexed wiring and unroll

Shape:

- `C1` contains `X(DOMAIN)` and `for x in astichi_for(DOMAIN): H(step)`
- `S1` builds `B1` without binding `DOMAIN`
- `S2` applies `bind B1 {DOMAIN=(...)}` and wires indexed children
- `S2` builds with `unroll="auto"` or `True`

Assertions:

- late bind succeeds
- indexed target resolution sees the later-bound domain
- unrolled order matches domain order
- materialized source contains no `astichi_for`

Variant:

- same test for list and tuple domains

### 8.3 `test_v3_spine_stage_built_import_demand_bound_later`

Purpose:

- prove that a stage-built composable can retain an unresolved identifier demand
  (`I(name)`) and receive the binding only in a later stage

Shape:

- `C1` contains `astichi_import(counter)` and updates `counter`
- `S1` builds `B1` with the demand unresolved
- `S2` inserts `B1` into a root that owns or exports the outer counter
- bind later via marker-driven variable binding, for example:
  - `astichi_export(counter)` surviving the stage boundary and consumed by
    `astichi_import(counter)`
  - or `builder.assign.B1.counter.to().Root.counter` where the source/target
    sides are still expressed through import/pass/export-capable snippets

Assertions:

- later-stage binding resolves the demand
- runtime output reflects the outer binding, not a shell-local leak
- do not use `arg_names=` in this staged spine; keep the focus on
  import/pass/export plus `assign`

### 8.4 `test_v3_spine_descendant_ref_paths_survive_stage_boundary`

Purpose:

- prove that descendant shell refs are preserved across `build()` boundaries in
  the same fluent shape the public API uses

Shape:

- `S1` builds `B1` with at least two nested descendants
- `S2` reuses `B1` and inserts it under another root
- inspect the pre-materialize merged tree from `S2.build()`

Assertions:

- the merged tree contains block shells with `ref=...` in fluent syntax
- prefixed descendant refs reflect the later-stage insertion point
- indexed descendants emit `ref=Foo.Parse[1, 2].Normalize`, not an internal
  tuple or reordered path encoding

### 8.5 `test_v3_spine_descendant_add_and_assign_match_same_shell_path`

Purpose:

- prove that additive wiring and identifier wiring both interpret the same
  descendant path against the same nested shell structure

Shape:

- `S1` builds `B1` with nested descendants such as `Pipeline.Root.Parse` and
  `Pipeline.Root.Right`
- `S2` uses one descendant path on the add side and another on the assign side
  against the same reused `B1`

Assertions:

- the add lands in the intended descendant shell only
- the assign resolves against the intended descendant supplier only
- no sibling descendant with the same leaf name is accidentally selected

### 8.6 `test_v3_spine_reuse_same_built_composable_with_distinct_bindings`

Purpose:

- prove per-instance isolation when the same `B1` is registered multiple times
  with different later-stage bindings

Shape:

- `S1` builds `B1` from a piece with `astichi_import(counter)` and, where
  needed, value-form `astichi_pass(source)` or `astichi_export(result)`
- `S2` adds `B1` twice as separate instances
- one instance gets identity binding, the other non-identity binding
- keep any keep-related variation on marker keep surfaces only; do not use
  `keep_names=...`

Assertions:

- bindings do not leak across instances
- emitted names and runtime outputs differ exactly as expected
- `keep` pins stay local to the intended instance

### 8.7 `test_v3_spine_export_survives_stage_boundary`

Purpose:

- prove that `E(name)` on a stage-built composable remains a usable supply at
  the next stage

Shape:

- `S1` builds `B1` that computes and exports `result`
- `S2` adds a reader piece that imports or otherwise consumes `result`
- connect using the explicit supply surface that the implementation supports

Assertions:

- `B1` still advertises the export after `S1.build()`
- later-stage consumer can use it without re-parsing or special casing
- materialized runtime result is correct

Note:

- if current implementation support is not complete for export consumption,
  this test should be written as a planned gap item, not forced prematurely

## 9. Focused matrix tests

These are short tests, ideally parameterized.

### 9.1 Ordering matrix

Purpose:

- isolate order semantics apart from other surfaces

Parameters:

- stage depth: `1`, `2`, `3`
- nesting depth: flat vs nested
- order pattern:
  - `0, 1`
  - `1, 0`
  - `0, 0` with first-added tie

Assertions:

- exact trace order
- tie stability remains insertion-ordered

### 9.2 Identifier wiring matrix

Purpose:

- cover the staged identifier-binding surfaces we want to exercise in V3

Demand source:

- `I(name)` (`astichi_import`)

Binding surface:

- `builder.assign.<Src>.<inner>.to().<Dst>.<outer>`

Binding model in V3 staged coverage:

- demand side is expressed with `astichi_import(...)`
- cross-stage supplier publication uses `astichi_export(...)`
- value-form scoped reads use `astichi_pass(...)`
- `builder.assign` is the builder-level wiring surface under test

The older `arg_names=` surfaces already have lower-level coverage and should not
be the main mechanism in the new staged matrix.

Likewise, the older `A(name)` / `__astichi_arg__` demand form is not the focus
of the new staged matrix; keep the V3 identifier stories on
`import` / `pass` / `export`.

Rename mode:

- identity
- non-identity

Assertions:

- resolved name appears exactly where expected
- unresolved slot rejects at the correct phase

Add a ref-path dimension:

- root-only
- descendant source path
- descendant target path

Add a registration-order dimension:

- target already registered
- forward-declared root target
- forward-declared deep target (current rejection case)

### 9.3 Keep-resolution matrix

Purpose:

- prove keep pins interact correctly with staged reuse and collisions

Keep surface:

- `astichi_keep(name)`
- `name__astichi_keep__`

Collision site:

- sibling roots
- inner shell vs outer scope
- reused `B1` added twice with different keep sets

Assertions:

- pinned spelling survives where intended
- unrelated scopes still rename apart
- keep does not silently widen to all reused instances

### 9.4 Delayed-unroll matrix

Purpose:

- isolate stage timing for `astichi_for`

Parameters:

- domain source:
  - literal tuple in source
  - bind-fed tuple
  - bind-fed list
- bind stage:
  - before `S1.build()`
  - after `B1`
- unroll mode:
  - `"auto"` via indexed edges
  - `True`

Assertions:

- unroll timing matches expectation
- indexed holes route to the correct synthetic names
- unresolved domain rejects when required

Also include at least one descendant-ref case where the addressed shell path
contains indices, so unroll interacts with descendant addressing and emitted
`ref=` metadata together.

### 9.5 Expression/variadic staged matrix

Purpose:

- ensure staging is not block-only

Hole shape:

- scalar expression
- positional variadic
- named variadic

Source shape:

- direct leaf
- stage-built composable reused later

Assertions:

- emitted value order is correct
- materialized source contains no residual markers

## 10. Scope-leak coverage

This needs two distinct buckets.

### 10.1 Current-contract tests

These should pass now.

They prove:

- unwired free names do not accidentally capture outer bindings
- strict scope isolation renames apart instead of silently guessing

These are not failures; they are contract tests.

### 10.2 Future soundness tests

These belong to the still-open soundness work.

They should be added when the owning behavior lands:

- undeclared cross-scope free-name references reject clearly
- unresolved implied demands reject at `materialize()`

Do not write these as permanent xfails. Add them when the behavior is ready.

## 11. Proposed helper structure in `tests/`

The new tests should not be assembled out of raw multiline strings only. Use
small helper factories so the test intent stays readable.

Recommended helpers:

- `make_trace_leaf(label: str) -> BasicComposable`
- `make_trace_shell(prefix: str, suffix: str) -> BasicComposable`
- `make_accumulator_root(counter_name: str = "total")`
- `make_import_step(name: str, delta: int)`
- `make_pass_through(name: str)`
- `make_pass_producer(name: str, value: int)`
- `make_export_piece(name: str, expr: str)`
- `assert_shell_refs(piece, expected_refs: list[str])`
- `assert_ref_targeting(piece, ref: str, hole: str, expected_sources: list[str])`

Helper policy:

- semantic tests should prefer runtime behavior or localized tree assertions
  over brittle whole-source string matching
- metadata tests should assert the fluent `ref=...` spelling directly, because
  emitted-source metadata syntax is now part of the contract
- `exec_materialized(comp) -> dict[str, object]`
- `run_trace(comp) -> list[str]`

Use helpers to make:

- order assertions exact
- stage structure obvious
- parameterized test cases small

## 12. API pressure and testability

If the tests become awkward because identifier aliasing or staged rebinding
cannot be expressed cleanly, that is signal, not noise.

Testability is a deliverable here.

Possible pressure points:

- later-stage identifier rebinding on already-built composables
- clearer export-consumption surface across stage boundaries
- builder-level helper for identifier wiring on target handles once the
  remaining IDENTIFIER supply work lands

Do not contort the tests to hide an API gap if the API is the real problem.

## 13. Recommended delivery order

Write tests in this order.

1. focused ref-path rejection matrix
2. `test_v3_spine_multistage_deep_order_trace`
3. `test_v3_spine_late_bind_external_then_unroll_in_later_stage`
4. `test_v3_spine_stage_built_import_demand_bound_later`
5. `test_v3_spine_reuse_same_built_composable_with_distinct_bindings`
6. ordering matrix
7. identifier wiring matrix
8. keep-resolution matrix
9. expression/variadic staged matrix
10. export-survival staged test
11. future soundness tests only when their owning behavior lands

## 14. Exit criteria

This plan is complete when:

- deep nested order is covered by at least one exact-trace staged test
- the ref-path rejection matrix locks unknown/ambiguous/duplicate descendant
  resolution behavior directly
- late `bind(...)` on a stage-built composable is covered directly
- late identifier binding on a stage-built composable is covered directly
- stage-built composable reuse with distinct bindings is covered directly
- at least one staged expression/variadic test exists
- at least one export-across-stage test exists, or the missing surface is
  explicitly documented as blocked
- helper factories exist so new staged-composition tests can be added cheaply

If these land, Astichi will have a materially stronger staged-composition test
story than it has today.
