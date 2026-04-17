# Astichi Single-Source Summary

This is the active summary document for Astichi.

Use this first. It is intentionally self-contained. It should be enough for a
new AI or engineer to continue the project without reading the rest of
`dev-docs/`.

Historical design/progress material exists under `dev-docs/historical/`, but it
is frozen and not required for active work.

Detailed issue write-ups live in `dev-docs/v2_issues/`. This summary is the
active handoff; the issue files are the deeper design notes behind the open
items.

## 1. Current snapshot

- Goal: ahead-of-time composition of Python source snippets via valid-Python
  marker syntax, additive builder wiring, build-time merge, materialize-time
  hygiene, and emit-time round-trip support.
- Public package exports today: `astichi.compile`, `astichi.build`,
  `astichi.Composable`.
- Implemented V2 work:
  - V2 Phase 1 external bind is complete.
  - V2 Phase 2 loop unroll has not started.
  - V2 Phase 3 polish has not started.
- Test status as of 2026-04-17:
  - full suite: `163 passed, 1 xfailed`
  - the sole xfail is the known materialize soundness gap for self-referential
    rename (`tests/test_materialize.py::test_materialize_gap3_self_ref_rename_xfail`)
- Current next concrete action:
  - implement loop-domain resolution in
    `src/astichi/lowering/unroll_domain.py`
  - add focused coverage in `tests/test_unroll_domain.py`

## 2. Governing principle and non-negotiable rules

### 2.1 Governing composition model

Astichi composes Python source at build time. Composition is recursive and may
remain partial.

The governing rule is:

- every input to a piece is in one of three states:
  - undefined: supply me from outside
  - defined: I have this; do not isolate me from it
  - free: neither; hygiene manages it
- markers exist to enumerate those states
- a state without a marker is an undocumented affordance
- a marker without a state is dead weight
- both are bugs

This is the framework behind the identifier-shape and cross-scope work:

- Issue 005 fills in the within-scope identifier state grid
- Issue 006 fills in the boundary crossings between Astichi scopes
- Issue 004 is the soundness gate that rejects silent crossings or silent
  undefined state

### 2.2 Non-negotiable rules

These are the rules that should not be re-litigated during implementation.

- Source is authoritative.
  - If emitted source is edited, the edited source wins.
  - Provenance may restore AST/source-location information only.
  - Provenance must not carry holes, binds, inserts, exports, builder graph
    state, or hidden semantic payloads.
- Emitted source must remain valid Python.
- Marker arguments are identifier-like references, not string literals.
- The builder is additive-first.
  - No replacement semantics.
  - No deep descendant traversal.
  - No optional-offer semantics.
- The fluent builder is a DSL over a plain raw API.
  - Every fluent operation should have a raw equivalent.
- Hygiene runs once, inside `materialize()`, when markers are in final
  position.
- A recognized marker with no consumer is a bug.
  - Reject it at the materialize gate rather than silently tolerating it.
- Preserve lexical keep semantics.
  - `astichi_keep(name)` means that spelling is pinned and must not be renamed.
- Pre-materialize `emit()` and `materialize()` have different contracts.
  - pre-materialize `emit()` preserves markers and supports marker-bearing
    round-trip via `emit()` -> `compile()`
  - `materialize()` closes hygiene, strips executable-only markers, and rejects
    unresolved mandatory state
  - `materialize().emit(provenance=False)` must be executable Python with no
    surviving marker call sites
- Implementation stays layered.
  - `frontend -> lowering -> hygiene -> model -> builder -> materialize -> emit`
- Do not store absolute filesystem paths in committed docs/config/examples/tests.

## 3. Public surface that exists today

### 3.1 Compile

`astichi.compile(source, file_name=None, line_number=1, offset=0)`

- Parses source into a composable.
- Uses ghost-padding rather than AST line-number rewriting:
  - prepend `line_number - 1` newlines
  - prepend `offset` spaces only for single-line snippets
- If the single-line offset causes `IndentationError`, parse again without the
  column padding.
- Returns a `FrontendComposable`, which is also a `Composable`.

This behavior is locked. Do not replace it with post-parse AST walks to rewrite
locations.

### 3.2 Build

`astichi.build() -> BuilderHandle`

Current fluent surface:

- `builder.add.A(comp)`
- `builder.A.slot.add.B(order=0)`
- `builder.A.slot[0]`
- `builder.A.slot[0, 1]`
- `builder.build()`

Current builder ordering rule:

- lower `order` inserts first
- equal `order` resolves by first-added edge first

### 3.3 Composable

Abstract surface:

- `emit(provenance: bool = True) -> str`
- `materialize() -> object`

Concrete carrier:

- `BasicComposable`
  - immutable dataclass
  - fields: `tree`, `origin`, `markers`, `classification`,
    `demand_ports`, `supply_ports`, `bound_externals`
  - method: `bind(mapping=None, /, **values) -> BasicComposable`

### 3.4 Emit, materialize, and provenance contract

Current implementation reality:

- pre-materialize `emit()` preserves markers and is intended to recompile into a
  structurally equivalent composable
- `materialize()` strips/realizes the executable marker surface and closes
  hygiene
- `materialize().emit(provenance=False)` is expected to be runnable Python
- `emit(provenance=True)` appends one trailing comment:
  - `# astichi-provenance: <payload>`
- round-trip helpers already exist in `src/astichi/emit/api.py`
- comment form is the tested implementation reality

There is still a docs/code drift on this format; see §9.4.

## 4. Marker surface: current status

| Marker / surface | Status | Notes |
|---|---|---|
| `astichi_hole(name)` | implemented | Demand port. Shape inferred from AST position. |
| `@astichi_insert(name, order=...)` | implemented | Block-form supply. Must match a hole. |
| `astichi_insert(name, expr)` | implemented | Expression-form supply. Must match a hole. |
| `astichi_keep(name)` | implemented | Pins lexical spelling; stripped during materialize. |
| `astichi_export(name)` | implemented | Supply-side export; stripped during materialize. |
| `astichi_bind_external(name)` | implemented | External literal bind demand. |
| `astichi_for(domain)` | recognized only | Loop-unroll semantics not implemented yet. |
| `astichi_bind_once(name, expr)` | recognized only | No active semantic owner in current V2 work. |
| `astichi_bind_shared(name, expr)` | recognized only | No active semantic owner in current V2 work. |
| `name__astichi__` / `astichi_definitional_name` | legacy/incomplete | Current code recognizes it, but the real identifier-shape model is not done; see §9.2. |

Important distinction:

- `recognized` does not mean `semantically complete`
- do not build new features on top of recognized-only markers as if they are
  finished surface area

Current shape vocabulary in code:

- `SCALAR_EXPR`
- `BLOCK`
- `IDENTIFIER`
- `POSITIONAL_VARIADIC`
- `NAMED_VARIADIC`

## 5. What is already implemented and working

### 5.1 Core pipeline

The V1 core path exists and is exercised:

- compile
- marker recognition
- permissive hygiene classification
- immutable composable construction
- builder graph creation
- build merge
- materialize
- emit
- provenance encode/decode/verify

### 5.2 External bind (V2 Phase 1)

Shipped behavior:

- `BasicComposable.bind(mapping=None, /, **values)`
- kwargs win over positional mapping on key collision
- keys must be valid identifiers
- unknown keys reject
- rebinding an already-bound external rejects
- values are restricted to:
  - `None`
  - `bool`
  - `int`
  - `float`
  - `str`
  - recursive `tuple`
  - recursive `list`
- unsupported values reject:
  - `dict`
  - `set`
  - `bytes`
  - callables
  - arbitrary objects
  - recursive containers
- bind substitution is scope-aware
- `materialize()` rejects unresolved `bind_external` demands

### 5.3 Materialize and gate behavior

Current materialize behavior that is already in place:

- unresolved `astichi_hole(...)` rejects
- unresolved `astichi_bind_external(...)` rejects
- unmatched block-form `@astichi_insert(name)` rejects
- unmatched bare statement `astichi_insert(name, expr)` rejects
- matched source-level inserts flatten into hole positions
- builder-added contributions become insert shells before materialize, then are
  flattened and hygienically renamed if needed
- residual `astichi_keep`, `astichi_export`, and current
  `astichi_definitional_name` markers are stripped

### 5.4 Hygiene

Implemented hygiene building blocks:

- permissive vs strict unresolved-name analysis
- keep-name preservation
- scope identity assignment for fresh Astichi scopes
- rename-on-collision with suffix form:
  - `name__astichi_scoped_<n>`
- expression-form insert wrappers receive fresh Astichi scope treatment

Known limitation:

- one materialize soundness gap is still xfailed; see §9.3

## 6. Code map

These are the active ownership points in the codebase.

- `src/astichi/frontend/api.py`
  - public `compile`
  - origin padding
- `src/astichi/lowering/markers.py`
  - marker recognition
  - marker capability objects
- `src/astichi/lowering/external_bind.py`
  - Phase 1 bind substitution engine
- `src/astichi/hygiene/api.py`
  - name classification
  - scope identity
  - rename pass
- `src/astichi/model/basic.py`
  - `BasicComposable`
  - `bind`
- `src/astichi/model/ports.py`
  - demand/supply extraction
  - compatibility checks
- `src/astichi/model/external_values.py`
  - bind-value validation and AST conversion
- `src/astichi/builder/graph.py`
  - raw graph structures
- `src/astichi/builder/handles.py`
  - fluent builder DSL
  - indexed path accumulation
- `src/astichi/materialize/api.py`
  - `build_merge`
  - materialize gate
  - insert flattening
  - hygiene closure
- `src/astichi/emit/api.py`
  - source emission
  - provenance encoding/extraction/verification

Missing Phase 2 files that should be added next:

- `src/astichi/lowering/unroll_domain.py`
- `src/astichi/lowering/unroll.py`
- `tests/test_unroll_domain.py`
- `tests/test_unroll.py`

## 7. Current tests and where to extend them

Existing high-signal tests:

- `tests/test_frontend_compile.py`
  - compile origin padding and syntax-error origin behavior
- `tests/test_lowering_markers.py`
  - marker recognition
- `tests/test_hygiene.py`
  - name classification, scope identity, collision renaming
- `tests/test_model.py`
  - port extraction
- `tests/test_external_values.py`
  - bind value-shape policy
- `tests/test_external_bind.py`
  - scope-aware external substitution
- `tests/test_bind_external.py`
  - public `.bind(...)`
- `tests/test_build_merge.py`
  - builder merge behavior
- `tests/test_materialize.py`
  - materialize gate and end-to-end semantics
- `tests/test_emit.py`
  - source emission and provenance

Focused test commands:

- full suite:
  - `uv run --with pytest pytest -q`
- typical focused runs:
  - `uv run --with pytest pytest tests/test_unroll_domain.py -q`
  - `uv run --with pytest pytest tests/test_unroll.py -q`
  - `uv run --with pytest pytest tests/test_build_merge.py -q`
  - `uv run --with pytest pytest tests/test_materialize.py -q`

## 8. Locked decisions that new work must respect

These decisions are already made and should be treated as stable.

- Compile origin padding is done by source padding, not AST coordinate rewrites.
- Column offset matters only for single-line snippets.
- Builder target addressing is root-instance-first.
- Indexed target addressing already uses `TargetHandle.__getitem__`.
  - Phase 2 must consume the stored path.
  - Phase 2 must not redesign the handle.
- Equal additive edge order resolves by insertion order.
- `bind()` is snapshot-based and returns a new immutable composable.
- `materialize()` currently returns another `BasicComposable`, not a code object.
- Provenance defaults to `True` on `emit`.
- Provenance is all-or-nothing from the public surface.
- Unroll is an additive V2 feature, not a reason to widen the surface into
  runtime parameter-dict domains or replacement semantics.

## 9. Critical incomplete areas

This section is the real handoff. These are the incomplete or misleading areas
that matter for the rest of the project.

### 9.1 V2 loop unroll is still entirely open

What is missing:

- domain resolution
- body-copy unroll engine
- hole renaming with `__iter_i`
- loop-variable literal substitution
- indexed-edge resolution against synthetic names
- `build(unroll="auto" | True | False)` integration

Constraints already decided:

- supported V2 domains:
  - tuple literals
  - list literals
  - `range(...)` with literal ints
  - domains that become one of the above after `bind()`
- all-or-nothing rule:
  - indexed addressing implies unroll
  - `unroll=False` plus indexed edges must reject
- unroll introduces no fresh Astichi scopes
- macro-style accumulation must still work across unrolled copies
- same-scope loop-variable rebind rejects
- cross-scope shadowing is respected
- name-bearing markers may not use the loop variable as the marker name

### 9.2 Identifier-shape and cross-scope composition are not actually done

Current reality is misleading:

- code still has a legacy `_DefinitionalNameMarker`
- it uses `__astichi__`
- it applies only to class/def names
- it is currently exposed as a supply port
- materialize strips it
- the call form `astichi_definitional_name(x)` is half-ghost behavior:
  - lowering does not recognize it as a real marker
  - residual-marker cleanup still strips it
  - do not preserve or extend this behavior

That is not the intended model.

The actual model that still needs to be implemented is:

- within one Astichi scope, identifier shape has three states:
  - undefined: `name__astichi_arg__`
  - defined/preserved: `name__astichi_keep__`
  - free: plain identifier
- parameter identity is one logical slot per:
  - `(stripped_name, Astichi scope)`
- every occurrence in that slot resolves atomically
  - class/function names
  - args
  - `ast.Name` load/store
  - relevant attribute-name sites if explicitly modeled
- the module is a valid outermost Astichi scope
  - this is the `astichi_script` case
  - one logical arg may appear at module scope across `ClassDef.name`,
    `Call.func`, and `astichi_export(...)` and must resolve as one parameter
- unresolved arg identifiers must gate `materialize()`
- keep suffixes must strip after hygiene
- no suffix may survive emit

Recommended simplification:

- treat the identifier-shape problem as one pipeline extension with two layers:
  - layer 1: within-scope identifier slots (`__astichi_arg__`,
    `__astichi_keep__`)
  - layer 2: cross-scope threading (`astichi_import`, `astichi_pass`)

Do not keep the old `__astichi__` surface alive as a parallel system.

Cross-scope threading decisions that are already locked:

- `astichi_import(name)` and `astichi_pass(name)` are boundary markers for the
  immediately enclosing Astichi scope only
  - no scope-skipping
  - multi-hop crossing requires explicit chaining through intermediate scopes
- placement rule:
  - these markers are declarations, not actions
  - they must appear at the top of the inner scope body, before real
    statements
- `astichi_pass(name)` must pin both scopes
  - pin the name in the inner scope
  - also add it to the outer preserved set at the splice point
- interaction matrix that must be preserved:
  - `import + pass` on the same name: reject
  - `import + __astichi_arg__`: reject
  - `import + __astichi_keep__`: reject
  - `pass + __astichi_arg__`: valid
  - `pass + __astichi_keep__`: valid
  - `pass + astichi_export`: valid
  - `import + astichi_export`: reject

### 9.3 Materialize soundness still has open gaps

Open gaps:

- Gap 1: cross-scope free-name fall-through
  - inserted code can accidentally capture an outer name without declaring it
- Gap 2: implied demands do not currently gate `materialize()`
  - `materialize()` may emit code that `NameError`s at runtime
- Gap 3: self-referential rename
  - `total = total + 1` inside a fresh Astichi scope can become
    `total__astichi_scoped_1 = total__astichi_scoped_1 + 1`
  - this is the current xfail

Resolved already:

- Gap 4 unmatched insert shell survival is fixed

How these interact:

- Gap 1 is really the undeclared-cross-scope version of the identifier-threading
  problem in §9.2
- Gap 2 is the materialize-gate version of “undefined names must be explicit”
- Gap 3 is a hygiene/read-before-write problem inside fresh Astichi scopes

Practical rule:

- do not call the project sound until all three open gaps are closed

### 9.4 Provenance format still has one low-priority drift

Current code and tests use:

- trailing comment `# astichi-provenance: ...`

Some design docs still describe:

- `astichi_provenance_payload("...")`

This is low priority but should be resolved once, then left alone.

### 9.5 Recognized-only markers are a trap

`astichi_bind_once`, `astichi_bind_shared`, `astichi_for`, and the legacy
identifier marker surface are currently easy to over-read as “supported”.

Do not silently expand semantics around them unless the summary document is
updated and the new owner step is added to the plan.

## 10. Open issue stack in priority order

There are two orderings to keep straight:

- execution order:
  - Phase 2 unroll remains the next code to write because it is already the
    active track and is mechanically isolated from the identifier redesign
- semantic priority:
  - Issue 006 is still the #1 blocking unresolved composition issue
  - it defines how names cross Astichi scope boundaries
  - nothing beyond the current isolated Phase 2 work should widen semantics
    without respecting 006

The current open issues reduce to this order.

### 10.1 Semantic blocker order

Treat these as one cluster, not as unrelated tickets.

1. `006` cross-scope identifier threading
   - top semantic blocker
   - boundary crossings must be explicit and local
   - `astichi_import(name)` for outer -> inner
   - `astichi_pass(name)` for inner -> outer
2. `005` within-scope identifier slots / definitional replacement
   - replace legacy `__astichi__`
   - add `__astichi_arg__`
   - add `__astichi_keep__`
   - make identifier shape demand-side, not fake supply-side
3. `004` materialize soundness closure
   - undeclared crossings reject
   - unresolved implied demands reject
   - self-referential rename fixed or rejected clearly
4. `003` provenance format drift
   - low priority

Implementation note:

- 006 is the governing design priority
- some of the code scaffolding may still start with 005-style within-scope slot
  machinery because 006 depends on atomic grouped identifier resolution
- do not treat that scaffolding order as a reprioritization of 006

## 11. Remaining development plan

This is the precise rest-of-project plan in execution order.

### 11.1 Current execution track: finish the published Phase 2

Do these next.

1. `2a` Domain resolution
   - add `src/astichi/lowering/unroll_domain.py`
   - accept:
     - tuple literal of literals
     - list literal of literals
     - `range(int)`, `range(int, int)`, `range(int, int, int)`
   - reject all other domain shapes clearly
   - tests:
     - `tests/test_unroll_domain.py`
2. `2b` Unroll engine
   - add `src/astichi/lowering/unroll.py`
   - deep-copy body per iteration
   - substitute loop-variable `Load` sites with literals
   - rename hole names to `name__iter_i`
   - respect scope shadowing
   - reject same-scope loop-variable rebind
   - reject name-bearing marker arg == loop variable
   - tests:
     - `tests/test_unroll.py`
3. `2c` Indexed-path edge resolution
   - extend `src/astichi/materialize/api.py`
   - consume existing `TargetRef.path`
   - map path to synthetic `__iter_...` target names
   - reject out-of-range and non-unrolled indexed references clearly
   - tests:
     - extend `tests/test_build_merge.py`
4. `2d` `build(unroll=...)` integration
   - extend `BuilderHandle.build`
   - accept `unroll="auto"` default, `True`, `False`
   - auto-detect unroll when indexed edges exist
   - reject `unroll=False` plus indexed edges
   - tests:
     - extend `tests/test_build_merge.py`
5. `2e` Phase 2 gate
   - full suite green
   - bind-fed literal domain end-to-end tests land
   - provenance round-trip still works on unrolled output

### 11.2 Immediately after Phase 2, schedule the identifier cluster

The current published V2 plan does not yet absorb this cluster. It should.

This section is execution order, not semantic priority. 006 remains the
governing blocker for identifier semantics; Phase 2 stays first only because it
is already isolated and in flight.

Recommended execution order:

1. Lock the 006 rules into the active plan
   - no scope-skipping
   - top-of-scope declaration placement
   - dual pinning for `astichi_pass`
   - interaction-matrix rejection rules
2. Identifier slots foundation from 005
   - change the legacy identifier marker into the real identifier-demand model
   - add grouped occurrence tracking per `(stripped_name, Astichi scope)`
   - move identifier resolution into materialize before hygiene
   - add keep-strip pass after hygiene
3. Boundary-threading implementation for 006
   - add `astichi_import`
   - add `astichi_pass`
   - extend ports, hygiene pins, and materialize resolution
4. Soundness closure for 004
   - gate undeclared crossings
   - gate unresolved implied demands
   - fix or reject self-referential rename

Why this order:

- Phase 2 is already the active execution path and is mechanically isolated
- 006 is the semantic blocker for sound composition
- 005 and 006 are coupled enough that they should be executed as one cluster
- the within-scope slot machinery is the likely code foundation, but it must be
  implemented against the 006 rules rather than as a separate design track

### 11.3 Then finish Phase 3 polish

After Phase 2 and the identifier cluster are stable:

1. `3a` shared scope-boundary helper
2. `3b` user docs
3. `3c` deferred-features register update
4. `3d` source-origin diagnostics
5. `3e` error-timing contract
6. `3f` marker-preserving skeleton emission
7. `3g` `compile_to_code`
8. `3h` final V2 exit gate

Keep this ordering:

- diagnostics before error-timing docs
- marker-preserving emit after the semantic surfaces are stable
- `compile_to_code` last; it is thin and depends on stable emit behavior

### 11.4 Low-priority cleanup

After the major semantic work:

1. resolve provenance format drift
2. either fully own or explicitly retire recognized-only markers not in active
   scope

## 12. Delivery discipline

For each real substep:

- change only the owning layer unless the step explicitly spans layers
- add focused tests first or alongside the change
- run focused tests
- run the full suite before declaring the step complete
- update progress tracking
- if following roll-build discipline, commit and tag by step

Soft implementation rule:

- keep each substep small enough that it can be reviewed and reverted
  independently

## 13. If you are taking over the project right now

Do this, in order:

1. read this file only
2. confirm the current suite still passes
3. implement `2a`
4. implement `2b`
5. implement `2c`
6. implement `2d`
7. run the Phase 2 gate
8. fold the identifier cluster into the active plan and implement it in the
   order from §11.2
9. finish Phase 3 polish
10. only then spend time on provenance drift or recognized-only marker cleanup

That path is the shortest route to a sound V2 without widening the design.
