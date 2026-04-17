# V2 progress register

Authoritative progress tracker for Astichi V2.

V1 closed and archived in `historical/`. V2 scope is documented in
`V2Plan.md`; design specs are:

- `AstichiApiDesignV1-BindExternal.md`
- `AstichiApiDesignV1-UnrollRevision.md`
- `AstichiApiDesignV1-MarkerPreservingEmit.md`

## Current status

- Active phase: **Phase 1 — external bind** (in progress)
- Active sub-phase: `1b` (demand port extraction for
  `astichi_bind_external`)
- Next concrete action: extend `src/astichi/model/ports.py` so
  `extract_demand_ports` emits bind-external demand ports and lock it
  with focused model tests.

## Conventions

Each sub-phase entry records:

- `Status`: `pending` | `in-progress` | `complete` | `deferred`
- `Layer`: implementation layer owning the work (per
  `AstichiImplementationBoundaries.md`)
- `Artifacts`: files expected to change / be created
- `Exit`: exit condition summary (detail in `V2Plan.md`)
- `Notes`: freeform running notes

## Phase 1 — external bind

Goal (summary): `composable.bind(name=value)` substitutes compile-time
values and removes `astichi_bind_external` markers; `materialize()`
rejects any remaining bind demand.

Spec: `AstichiApiDesignV1-BindExternal.md`.

### 1a. Value-shape policy and AST converter

- Status: complete
- Layer: `model`
- Artifacts:
  - `src/astichi/model/external_values.py` (new)
  - `tests/test_external_values.py` (new)
- Exit: converters handle all V1 literal types incl. nested tuple/list;
  non-literal inputs rejected with clear errors; depth guard tested.
- Notes: implemented `value_to_ast` and `validate_external_value` in
  `src/astichi/model/external_values.py`; focused tests landed in
  `tests/test_external_values.py`.

### 1b. Demand port extraction for `astichi_bind_external`

- Status: pending
- Layer: `model`
- Artifacts:
  - `src/astichi/model/ports.py` (extend)
  - `tests/test_model.py` (extend)
- Exit: `extract_demand_ports` emits the bind-external port per
  `BindExternal.md §5`.
- Notes: —

### 1c. Substitution engine (scope-aware)

- Status: pending
- Layer: `lowering`
- Artifacts:
  - `src/astichi/lowering/external_bind.py` (new)
  - possible helper in `src/astichi/asttools/`
  - `tests/test_external_bind.py` (new)
- Exit: `apply_external_bindings` performs scope-aware substitution;
  same-scope rebind and marker-arg conflicts rejected.
- Notes: the scope-boundary traversal is reused by 2b.

### 1d. `BasicComposable.bind(mapping, /, **values)` API

- Status: pending
- Layer: `model`
- Artifacts:
  - `src/astichi/model/basic.py` (extend)
  - `tests/test_bind_external.py` (new or extended)
- Exit: returns a new composable; unknown-key / re-bind / empty-bind
  behaviors match `BindExternal.md §6`.
- Notes: —

### 1e. `materialize()` integration

- Status: pending
- Layer: `materialize`
- Artifacts:
  - `src/astichi/materialize/api.py` (extend)
  - `tests/test_materialize.py` (extend)
- Exit: unresolved bind demand raises a clear materialize-time error;
  bound composables materialize end-to-end.
- Notes: —

### Phase 1 exit gate

- Status: pending
- Exit: all 1a–1e items `complete`; phase-wide tests green; provenance
  round-trip verified on a bound composable.

## Phase 2 — loop unroll (V1-lite)

Goal (summary): build-time unroll of `astichi_for` loops with literal
domains, including post-bind literals; scope-aware variable
substitution; `astichi_hole` target renaming via `__iter_i`.

Spec: `AstichiApiDesignV1-UnrollRevision.md`.

### 2a. Domain resolution

- Status: pending
- Layer: `lowering`
- Artifacts:
  - `src/astichi/lowering/unroll_domain.py` (new)
  - `tests/test_unroll_domain.py` (new)
- Exit: literal tuples/lists and `range(...)` with int literals accepted;
  other shapes rejected.
- Notes: —

### 2b. Unroll engine

- Status: pending
- Layer: `lowering`
- Artifacts:
  - `src/astichi/lowering/unroll.py` (new)
  - `tests/test_unroll.py` (new)
- Exit: per-iteration deep-copy, constant substitution, `__iter_i` hole
  rename, no fresh scopes, rejection modes enforced.
- Notes: reuses the scope-aware helper from 1c.

### 2c. Indexed-path edge resolution

- Status: pending
- Layer: `materialize` / `builder`
- Artifacts:
  - `src/astichi/materialize/api.py` (extend edge resolution)
  - `tests/test_build_merge.py` (extend)
- Exit: edge resolver translates non-empty `TargetRef.path` to the
  post-unroll synthetic target name; out-of-range and non-unroll cases
  rejected with clear diagnostics.
- Notes: `TargetHandle.__getitem__` path accumulation already exists
  (see `UnrollRevision.md §8.3`); this step does **not** modify the
  handle. Input contract: the path tuple shape as already recorded by
  the builder.

### 2d. `build()` integration

- Status: pending
- Layer: `builder` / `materialize`
- Artifacts:
  - `src/astichi/builder/handles.py::BuilderHandle.build` (extend)
  - `src/astichi/materialize/api.py::build_merge` (call unroll first)
  - `tests/test_build_merge.py` (extend)
- Exit: `unroll="auto"` / `True` / `False` honored; conflict cases
  rejected.
- Notes: —

### Phase 2 exit gate

- Status: pending
- Exit: all 2a–2d items `complete`; bind-feeds-unroll end-to-end
  tests green; round-trip provenance verified on unrolled output.

## Phase 3 — integration polish

### 3a. Shared scope-boundary helper

- Status: pending
- Layer: `asttools`
- Exit: bind and unroll substitution visitors share the scope helper.

### 3b. User-facing documentation updates

- Status: pending
- Layer: `docs`
- Exit: `docs/` reflects bind + unroll tutorial/reference entries.

### 3c. Deferred-feature follow-up

- Status: pending
- Layer: `docs`
- Artifacts:
  - `astichi/dev-docs/V2DeferredFeatures.md` (update)
- Exit: `V2DeferredFeatures.md` reflects shipped V2 items
  (§3.1, §4.1, §7.4, §9.1, §9.2, and the post-bind-literal subset of
  §5.1) in its §1 and confirms or updates the remaining items in §2.
  The frozen `historical/V1DeferredFeatures.md` is not edited.

### 3d. Source-origin diagnostics

Reinstates V1 deferred §9.2.

- Status: pending
- Layer: cross-cutting (`frontend`, `lowering`, `materialize`,
  `builder`)
- Artifacts:
  - error-raise sites across `src/astichi/**`
  - possible helper in `src/astichi/asttools/`
  - `tests/test_diagnostics.py` (new)
- Exit: per-layer diagnostics golden tests confirm each user-visible
  error names file/line/marker; no regressions.
- Notes: polish pass, not a semantic change.

### 3e. Unified error-timing contract

Reinstates V1 deferred §9.1.

- Status: pending
- Layer: `docs`
- Artifacts:
  - `astichi/dev-docs/AstichiErrorTimingContract.md` (new)
  - cross-links from existing design docs
- Exit: contract doc enumerates every V2 error path with its timing
  phase and references the tests that lock it.
- Notes: depends on 3d so errors have concrete origin behavior to
  document.

### 3f. Marker-preserving (skeleton) emission

Reinstates V1 deferred §3.1. Spec:
`AstichiApiDesignV1-MarkerPreservingEmit.md`.

- Status: pending
- Layer: `emit` / `materialize` / `model`
- Artifacts:
  - `src/astichi/materialize/api.py` (factor `close_hygiene`)
  - `src/astichi/emit/api.py` (extend signature)
  - `src/astichi/model/basic.py` (`emit(mode=...)`)
  - `tests/test_marker_preserving_emit.py` (new)
- Exit: `emit(mode="markers")` preserves unresolved markers; round-trip
  through `astichi.compile` works; strict-mode error cites the
  skeleton alternative; provenance round-trip succeeds.
- Notes: markers-mode always runs the hygiene closure.

### 3g. `compile_to_code` adapter

Reinstates V1 deferred §7.4.

- Status: pending
- Layer: `emit` / `model`
- Artifacts:
  - `src/astichi/emit/api.py` (add helper)
  - `src/astichi/model/basic.py` (`compile_to_code`)
  - `tests/test_emit.py` (extend)
- Exit: returns a `types.CodeType` for a materialized composable that
  executes cleanly; rejects skeleton-mode input; `filename` threads
  into tracebacks.
- Notes: strict-mode only; narrow scope.

### Phase 3 exit gate

- Status: pending
- Exit: all 3a–3g items `complete`; V2 scope signed off.

## V2 exit

- Status: pending
- Exit: every phase gate above is `complete` and the V2 exit gate in
  `V2Plan.md §6` is satisfied.
