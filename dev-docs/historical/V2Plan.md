# V2 plan

This document is the execution plan for Astichi V2.

V2 adds two feature families on top of the V1 pipeline, plus a small polish
bundle that lands alongside them:

- **External bind** — `composable.bind(name=value)` + supporting port,
  substitution, and materialize integration.
- **Loop unroll** (V1-lite) — build-time unrolling of `astichi_for` with
  literal domains, including domains that become literal after `bind()`.
- **Phase 3 polish** — diagnostics citing source origins, a unified
  error-timing contract document, marker-preserving (skeleton) emission,
  and a `compile_to_code` adapter.

The detailed design for each feature lives in a dedicated addendum; this plan
refers to those documents as the normative specs and only breaks the work
into implementation steps.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md` (base V1 design)
- `astichi/dev-docs/AstichiApiDesignV1-BindExternal.md` (bind spec)
- `astichi/dev-docs/AstichiApiDesignV1-UnrollRevision.md` (unroll spec)
- `astichi/dev-docs/AstichiApiDesignV1-MarkerPreservingEmit.md`
  (skeleton emission spec)
- `astichi/dev-docs/IdentifierHygieneRequirements.md`
- `astichi/dev-docs/AstichiImplementationBoundaries.md`
- `astichi/dev-docs/AstichiInternalsDesignV1.md`
- `astichi/dev-docs/V2ProgressRegister.md`

Active V2-era tracker:

- `astichi/dev-docs/V2DeferredFeatures.md` (successor to the frozen
  V1 list; records V2 scope status and further-deferred items)

Historical references (frozen — do not edit):

- `astichi/dev-docs/historical/V1Plan.md`
- `astichi/dev-docs/historical/V1ProgressRegister.md`
- `astichi/dev-docs/historical/V1DeferredFeatures.md`

## 1. Plan structure

The plan uses phase-aligned numbering:

- Phase 1 (external bind) uses steps `1a`, `1b`, `1c`, ...
- Phase 2 (loop unroll) uses steps `2a`, `2b`, `2c`, ...
- Phase 3 (integration polish) uses steps `3a`, `3b`, ...

Each step declares:

- owner layer
- goal
- exit criteria
- required tests / verification

## 2. Ordering rationale

Bind ships before unroll because:

- Bind is a self-contained feature with clear exit criteria and no dependency
  on unroll.
- Bind introduces the scope-aware substitution visitor that unroll also
  needs; shipping bind first lets unroll reuse it as a helper rather than
  duplicate it.
- Bind broadens the class of programs that can benefit from unroll (post-bind
  literal domains per `AstichiApiDesignV1-BindExternal.md §8`).

## 3. Phase 1 — external bind

Spec: `AstichiApiDesignV1-BindExternal.md`.

Milestone goal: `BasicComposable.bind(mapping=None, /, **values)` returns
a new composable with `astichi_bind_external(name)` markers removed and
`Name(name, Load)` references substituted. `materialize()` rejects any
remaining bind demand. See `BindExternal.md §6.1` for the locked
signature.

### 1a. Value-shape policy and AST converter

- Owner layer: `model`
- Files:
  - new: `src/astichi/model/external_values.py`
  - new: `tests/test_external_values.py`
- Goal: implement `value_to_ast(value)` and `validate_external_value(value)`
  per `BindExternal.md §3, §4`.
- Exit: round-trip tests for all supported V1 types (int, float, str, bool,
  None, tuple, list, nested combinations); rejection tests for dict, set,
  object, callable; depth-limit test.

### 1b. Demand port extraction for `astichi_bind_external`

- Owner layer: `model`
- Files:
  - `src/astichi/model/ports.py` (extend `extract_demand_ports`)
  - `tests/test_model.py`
- Goal: emit a `DemandPort(name, SCALAR_EXPR, placement="expr",
  mutability="const", sources={"bind_external"})` for every recognized
  `astichi_bind_external(name)` marker per `BindExternal.md §5`.
- Exit: focused tests cover single marker, multiple markers, no
  regression on existing port extraction.

### 1c. Substitution engine (scope-aware)

- Owner layer: `lowering`
- Files:
  - new: `src/astichi/lowering/external_bind.py`
  - extend: `src/astichi/asttools/` (shared scope-boundary helper if needed)
  - new: `tests/test_external_bind.py`
- Goal: implement `apply_external_bindings(tree, bindings)` per
  `BindExternal.md §7`:
  - remove matching `astichi_bind_external(...)` statements
  - replace `Name(id=n, ctx=Load)` with `value_to_ast(bindings[n])`
  - honor scope boundaries (function/lambda/comprehension/for-target)
  - reject same-scope rebinding and marker-argument conflicts
- Exit: tests cover simple substitution, multi-name, scope shadowing (all
  recognized boundaries), same-scope-rebind rejection, marker-argument
  rejection.

### 1d. `BasicComposable.bind(mapping, /, **values)` API

- Owner layer: `model`
- Files:
  - `src/astichi/model/basic.py` (add `bind` method)
  - `tests/test_bind_external.py`
- Goal: implement `bind(mapping=None, /, **values)` per
  `BindExternal.md §6.1` (locked):
  - merge the positional mapping and keyword entries via
    `dict(**mapping, **values)` with kwargs winning on collision;
  - validate each resolved value (1a);
  - validate each resolved key (non-identifier rejected);
  - validate keys against existing demand ports (unknown-key error,
    re-bind error);
  - deep-copy tree, apply substitution (1c), re-run marker recognition
    and port extraction;
  - return a new `BasicComposable`.
- Exit: tests cover success (keyword form), success (mapping form),
  success (mixed mapping + keyword with kwargs winning on collision),
  non-identifier key rejection (mapping form), unknown-key rejection,
  re-bind rejection, partial bind (two sequential `bind()` calls),
  empty-bind no-op.

### 1e. `materialize()` integration

- Owner layer: `materialize`
- Files:
  - `src/astichi/materialize/api.py`
  - `tests/test_materialize.py`
- Goal: extend the mandatory-demand closure in `materialize_composable`
  to also reject unresolved `sources={"bind_external"}` demands per
  `BindExternal.md §6.2`.
- Exit: tests confirm that an unresolved bind demand raises a clear
  error at materialize, and that a fully bound composable materializes
  cleanly end-to-end.

### 1f. Phase 1 exit gate

- All Phase 1 tests pass under `pytest -p no:pyrolyze`.
- `emit()` of a bound composable produces valid Python that round-trips
  through provenance verification.
- `V2ProgressRegister.md` marks Phase 1 complete.

## 4. Phase 2 — loop unroll (V1-lite)

Spec: `AstichiApiDesignV1-UnrollRevision.md`.

Milestone goal: `build(unroll=...)` eliminates `astichi_for` loops with
supported domains by producing `N` copies of the loop body with the loop
variable substituted as `ast.Constant`, `astichi_hole` targets renamed with
`__iter_i` suffixes, and no fresh Astichi scopes introduced.

### 2a. Domain resolution

- Owner layer: `lowering`
- Files:
  - new: `src/astichi/lowering/unroll_domain.py`
  - new: `tests/test_unroll_domain.py`
- Goal: resolve domains per `UnrollRevision.md §7`:
  - `ast.Tuple` / `ast.List` of constants → direct
  - `ast.Call(Name("range"), [int literal]|[int, int]|[int, int, int])`
    → `range(...)` evaluated at build time
  - reject all other domain shapes with a clear message
- Exit: tests cover each accepted shape; rejection tests for non-literal
  domains, non-int literals inside `range`, and unsupported call names.

### 2b. Unroll engine

- Owner layer: `lowering`
- Files:
  - new: `src/astichi/lowering/unroll.py`
  - new: `tests/test_unroll.py`
- Goal: implement `unroll_loops(tree)` per `UnrollRevision.md §§5–6`:
  - deep-copy the loop body per iteration
  - substitute `Name(loop_var, Load)` with `ast.Constant(value)` in a
    scope-aware visitor (reuse helper from 1c)
  - rename `astichi_hole(name)` targets to `name__iter_i`
  - do **not** rename other Python-level names or introduce fresh
    Astichi scope boundaries
  - reject same-scope shadowing of the loop variable
  - reject name-bearing markers whose argument equals the loop variable
- Exit: tests cover
  - unrolling tuple / list / range domains (and post-bind literal
    domains per `UnrollRevision.md §10` "In scope for V2");
  - correct `__iter_i` rename of `astichi_hole` targets;
  - macro-style accumulator behavior (`total = total + x` works
    across copies because no fresh scope is introduced);
  - cross-scope shadowing honored by the substitution visitor (the
    loop variable reference inside an inner function / lambda /
    comprehension / for-target that rebinds the name is left
    untouched);
  - same-scope rebind of the loop variable rejected with a clear
    error (per `UnrollRevision.md §5.3`);
  - nested loops (outer resolves first, inner domain gets the outer
    iteration value literal-substituted before its own unroll).

### 2c. Indexed-path edge resolution

- Owner layer: `materialize` / `builder`
- Files:
  - `src/astichi/materialize/api.py` (edge resolution against the
    post-unroll target namespace)
  - `src/astichi/builder/handles.py` (read-only here; path
    accumulation via `TargetHandle.__getitem__` is already in place
    per `UnrollRevision.md §8.3`)
  - extend `tests/test_build_merge.py`
- Goal: teach the edge resolver (invoked during `build_merge`) to
  translate an edge whose `TargetRef.path` is non-empty into the
  synthetic target name produced by the 2b unroll pass (e.g.
  `slot__iter_0`, `slot__iter_0_1` for nested).
- Exit: tests cover
  - single-level indexing resolving against a post-unroll target;
  - multi-level indexing (nested loop, dotted `__iter_i_j`);
  - out-of-range path rejected at edge resolution time with a clear
    message citing the edge and the path tuple
    (`UnrollRevision.md §8.3`);
  - indexed edge against a target not produced by unroll (because
    `unroll=False`, or the target does not originate from
    `astichi_for`) rejected at edge resolution with a clear
    diagnostic suggesting `unroll=True` when applicable.
- Non-goals: no changes to `TargetHandle.__getitem__`; the path-tuple
  shape recorded by the builder is the input contract for this
  resolver, not something this step modifies.

### 2d. `build()` integration

- Owner layer: `builder` / `materialize`
- Files:
  - `src/astichi/builder/handles.py::BuilderHandle.build`
  - `src/astichi/materialize/api.py::build_merge` (call unroll before
    edge resolution)
  - `tests/test_build_merge.py`
- Goal: wire the unroll pass into `build()` per `UnrollRevision.md §6.1`:
  - accept `unroll="auto"` (default) | `True` | `False`
  - auto-detect from presence of indexed edges
  - explicit `True` forces unroll; `False` forbids it
- Exit: auto-detect tests, explicit override tests, conflict tests (e.g.
  `unroll=False` combined with indexed edges).

### 2e. Phase 2 exit gate

- All Phase 2 tests pass.
- End-to-end tests exercise `bind()` feeding unroll-literal domains.
- `emit()` + provenance round-trip verified on unrolled output.
- `V2ProgressRegister.md` marks Phase 2 complete.

## 5. Phase 3 — integration polish

Small follow-up items that only make sense once Phase 1 and Phase 2 are
both in. These reinstate specific V1-deferred items (see
`historical/V1DeferredFeatures.md`, via the active
`V2DeferredFeatures.md` tracker) where the implementation cost is
small and the benefit aligns with finishing the V2 surface.

Mapping to originally-deferred items (entries in the frozen V1 list;
current status is tracked in `V2DeferredFeatures.md §1`):

- 3d reinstates §9.2 (diagnostics citing source origins).
- 3e reinstates §9.1 (unified error-timing contract).
- 3f reinstates §3.1 (marker-preserving skeleton emission).
- 3g reinstates §7.4 (emission-vs-compile adapter).

### 3a. Shared scope-boundary helper

- Owner layer: `asttools`
- Goal: if 1c and 2b duplicate scope-boundary traversal logic, extract
  the shared parts into `src/astichi/asttools/scope.py` (or similar).
- Exit: substitution visitors in bind and unroll both route through the
  shared helper; no behavior change.

### 3b. User-facing documentation updates

- Owner layer: `docs`
- Goal: update `docs/` (per `AstichiUserDocumentationPlan.md`) with
  tutorial and reference entries for `bind()` and unroll semantics.
- Exit: user docs cover value-shape policy, scope rules, and the
  `unroll="auto"` contract.

### 3c. Deferred-feature follow-up

- Owner layer: `docs`
- Files:
  - `astichi/dev-docs/V2DeferredFeatures.md` (update)
- Goal: update the active V2 deferred-features tracker to reflect
  what actually shipped vs. what remained deferred. The frozen V1
  list (`historical/V1DeferredFeatures.md`) is **not** edited —
  the frozen-historical rule is preserved.
- Exit: every entry in `V2DeferredFeatures.md §1` (reinstated)
  references a shipped phase of `V2Plan.md`; every entry in §2
  (still deferred) is either confirmed or updated with the rationale
  discovered during V2 implementation; any new V2-era deferrals are
  recorded in §3 of that doc.
- Notes: Phase 3 items that reinstate specific V1-deferred entries
  (3d→§9.2, 3e→§9.1, 3f→§3.1, 3g→§7.4, and the Phase 1/2 items that
  reinstate §4.1 and the post-bind variant of §5.1) are the primary
  cross-off set.

### 3d. Source-origin diagnostics

Reinstates V1 deferred §9.2.

- Owner layer: cross-cutting (primarily `frontend`, `lowering`,
  `materialize`, `builder` error sites)
- Files:
  - existing error-raise sites across `src/astichi/**`
  - possible helper in `src/astichi/asttools/` for
    "format origin" / "format node location"
  - `tests/test_diagnostics.py` (new)
- Goal: thread `CompileOrigin` (and AST node `lineno`/`col_offset` when
  available) through all user-visible error messages, so that every
  error names the originating file, line, and, where relevant, the
  marker name.
- Exit: diagnostics golden tests cover a representative error per
  layer (lowering rejection, port validation, bind-time rejection,
  materialize gate, unroll rejection); each message includes the
  origin string. No regressions on existing tests.
- Notes: this is a polish pass, not a semantic change. Where errors
  do not currently have a node or origin to cite, we thread one
  through rather than invent synthetic locations.

### 3e. Unified error-timing contract

Reinstates V1 deferred §9.1.

- Owner layer: `docs`
- Files:
  - new: `astichi/dev-docs/AstichiErrorTimingContract.md`
  - cross-links from existing design docs to the new doc
- Goal: document every user-visible error in V2 in a single matrix
  that lists *what* fires *when* (parse / compile / add / build / bind
  / materialize / emit). The matrix becomes the normative contract;
  behavior elsewhere must conform to it.
- Exit: the contract doc exists, enumerates every current V2 error
  path, and references the tests that lock each timing. No code
  changes are required; mismatches discovered during writing are
  fixed as 3d work items or recorded as issues against 3f/3g.
- Notes: do this *after* 3d so every error path has a concrete
  origin-reporting behavior to document.

### 3f. Marker-preserving (skeleton) emission

Reinstates V1 deferred §3.1. Spec:
`AstichiApiDesignV1-MarkerPreservingEmit.md`.

- Owner layer: `emit` / `materialize` / `model`
- Files:
  - `src/astichi/materialize/api.py` (factor out `close_hygiene`)
  - `src/astichi/emit/api.py` (extend `emit_source` signature)
  - `src/astichi/model/basic.py`
    (`BasicComposable.emit` gains `mode` parameter)
  - `tests/test_marker_preserving_emit.py` (new)
- Goal: implement `emit(mode="markers")` per
  `AstichiApiDesignV1-MarkerPreservingEmit.md`:
  - factor `close_hygiene` out of `materialize_composable`
  - add `mode` parameter to `emit`
  - strict mode retains existing behavior; markers mode skips the
    unresolved-demand gate and preserves unresolved markers verbatim
- Exit: tests cover skeleton preservation of holes, unresolved binds,
  un-unrolled `astichi_for` loops; re-parse round trip; textual fixed
  point (skeleton → compile → skeleton is idempotent); strict-mode
  error message mentions markers-mode as an alternative; provenance
  round-trip succeeds on skeleton output.

### 3g. `compile_to_code` adapter

Reinstates V1 deferred §7.4.

- Owner layer: `emit` / `model`
- Files:
  - `src/astichi/emit/api.py` (add `compile_to_code` helper)
  - `src/astichi/model/basic.py`
    (`BasicComposable.compile_to_code(filename=...)`)
  - `tests/test_emit.py` (extend)
- Goal: provide a thin convenience over `compile(emit(), filename,
  "exec")` that returns a `types.CodeType`. Accepts an optional
  `filename` (default derived from `CompileOrigin`) and optional
  `mode=` that forwards to `emit`.
- Exit: tests verify the code object executes cleanly for a
  representative materialized composable; the `filename` threads into
  tracebacks; a skeleton-mode code object is rejected (skeleton text
  may contain marker calls that would `NameError` at runtime).
- Notes: strict-mode only for callable code; markers-mode artifact
  remains a source string. This is intentionally narrow.

### 3h. Phase 3 exit gate

- All 3a–3g items complete.
- Full V2 scope signed off in `V2ProgressRegister.md`.

## 6. V2 exit gate

V2 is considered complete when:

- All Phase 1, 2, and 3 exit gates are met.
- `composable.bind(...)`, indexed target addressing, and
  `build(unroll=...)` behave per the addendum specs under test.
- Round-trip (parse → build → materialize → emit → parse-again) is
  verified for representative bind + unroll programs.
- No new design-drift entries appear for bind / unroll.
