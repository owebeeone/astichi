# Full Self-Native Rust AST Plan

Status: implementation plan (pass 2 — roll-build ready after contract acceptance).

This track is separate from the incremental `perf-native/p*` roll-build in
`NativePerformancePlan.md`. That plan remains the hybrid-era record; **this plan
supersedes P7 closeout goals** for production full-native boundary work (P7
cleanup items fold into F5 here where they overlap).

Routes the native **production** path through Rust end-to-end; CPython `ast`
only at explicit artifact handoff. Public APIs stay stable.

Rationale: `NativeAstProbe.md`, `NativeDecisionProfile.md`.
Tags: `perf-native-full/*`.
Reviews: `scratch/FullSelfNativeRustAstPlan-Review5.5.md`,
`scratch/FullSelfNativeRustAstPlan-Review5.5-2.md`,
`scratch/FullSelfNativeRustAstPlan-Review3.5-1.md` (runtime invariants).

**Roll-build rule:** each tag leaves a coherent system. Do not start until **F0c**
(capability contract) and **F0b** (leak inventory) are accepted.

## Thesis

Native already owns parse (rustpython), package-v2 extraction, scope batch, and
materialize IR. Remaining cost is **duplicate Python `ast` work** on paths that
still pass the old hybrid capability gate, not Rust algorithm speed.

Work is boundary routing **plus** semantic parity (validators, materialize
surfaces, literal ABI, facade storage). Hybrid-native must not be mistaken for
full self-native.

## Self-native vs hybrid-native selection

The existing capability `native.full_lower_engine.current_surfaces.v1` is
**too coarse** for this plan. A build can satisfy that gate while still using
Python `ast.parse` on compile, Python materialize fallback, mirror replay, and
per-edge Python scope apply.

Introduce a **self-native capability family** (advertised incrementally per
slice; production guards assert these, not merely `engine=native`):

| Capability | Enables |
|------------|---------|
| `native.self_native.compile_validation.v1` | F3b–F3c validators on native IR |
| `native.self_native.no_python_parse_compile.v1` | F3d: no `ast.parse` on compile success path |
| `native.self_native.literal_payload_abi.v1` | F1b: overlay literals without `ast.unparse` |
| `native.self_native.scope_no_mirror_replay.v1` | F1b: native batch commit-only |
| `native.self_native.materialize_no_python_fallback.v1` | F4d: no Python lower materializer fallback |
| `native.self_native.current_surfaces.v1` | F4c complete surface list + F4e handoff |

**Selection policy:**

- `auto`: may use hybrid-native (`full_lower_engine`) until
  `self_native.current_surfaces.v1` is present; then prefer self-native when
  capable.
- explicit `native` with self-native request: fail with diagnostic if extension
  lacks required self-native capability (do not silently run hybrid hot path).
- F0a/F0b/F3/F4 guards and CI assert **self-native capabilities + counters**,
  not only `ASTICHI_LOWER_ENGINE=native`.

Document capability names in `capabilities.rs`, `EngineSelectionContract.md`,
and `native_engine/README.md` (F0c, F5).

## Production success path vs public slow paths

```text
Production success path (requires self_native.current_surfaces.v1):
  compile / bind / scope.build / to_executable_ast
    -> Python facade (handles, external object slots, diagnostics)
    -> native engine (parse, package, scope, materialize, hygiene)
    -> copy_python_ast once per final materialized module
    -> fix_missing_locations (separate counter; see F0b)
    -> caller compile(...) / exec(...)   # outside astichi

Public slow paths (allowed, slow_path_* counters, not on lifecycle import):
  .tree first access, emit(), emit_commented(), describe(),
  scope.inventory, structural snapshots, render_source,
  workspace copy_to_python_ast / to_source

Oracle / fallback: engine=python; hybrid-native for interim tags
```

## Explicit contracts

### A. Native compile validation parity (blocks F3d)

Ledger must cover **all** public `compile(...)` semantics, not only marker
walks.

| Gate / step | Module area | Native owner | Notes |
|-------------|-------------|--------------|-------|
| Source padding: `line_number`, `offset`, single-line indent fallback | `frontend/api.py` | F3b | Match `SyntaxError` / `IndentationError` filename and line behavior |
| `attach_astichi_source_file` metadata | frontend | F3b | Origin on nodes / diagnostics |
| `source_kind`: `authored` vs `astichi-emitted` | frontend | F3b | Emitted allows `astichi_insert` surfaces |
| Authored `astichi_insert` rejection | frontend | F3b | |
| Boundary marker placement | frontend | F3b | |
| Call-argument payload surface | frontend | F3b | |
| Parameter payload surface | frontend | F3b | |
| External-ref surface + desugaring | frontend | F3b | |
| Pyimport declaration validation | frontend | F3b | |
| Parameter-hole validation | frontend | F3b | |
| Boundary interaction matrix | frontend | F3b | |
| `_validate_keep_names` | frontend | F3b | |
| `_validate_arg_names` + eager bind_identifier effect | frontend | F3b | |
| Parser grammar / version matrix | native parse | F3a policy, F3b impl | See §A.1 |
| Marker recognition | markers | F3b | From native package |
| Name analysis (permissive) | hygiene | **F3b mandatory** | Production metadata source |
| Demand/supply port extraction | ports | **F3b mandatory** | Not debug-only projection |
| Inventory for `describe()` | inventory | F5 slow-path only | |

**§A.1 Parser matrix policy (decide in F3a, not F3d):**

Rustpython may reject syntax CPython accepts (known project risk). Policy
options (pick one in F3a doc):

1. **Strict native:** self-native mode supports only the Astichi syntax matrix
   validated in CI; explicit `native` fails with clear diagnostic on mismatch.
2. **Auto fallback:** `auto` falls back to Python parse on native syntax
   rejection; explicit `native` still fails clearly. On fallback, increment
   `native_parser_grammar_fallback` (or equivalent) and record an
   `EngineSelectionEvent` with `reason_key=native_grammar_unsupported` so silent
   hybrid regressions are visible in CI/telemetry.

Differential tests (F3c) include matrix fixtures per supported Python version.

**F3c diagnostic parity (do not assert exact CPython message strings):**

- **Strict:** exception type, filename, line, column/offset (when available).
- **Loose:** message body via substring/regex for error class (e.g. invalid
  syntax, unexpected indent), not byte-for-byte equality across Python versions
  or rustpython wording.

**F3 slices:** F3a ledger + policy → F3b implementation → F3c oracle → F3d cutover.
Name analysis and port extraction are **required F3b rows**, not deferred.

### B. Public `.tree` / `emit()` / `describe()` (implementation: F2d before F3d)

Contract unchanged: APIs remain callable; production lifecycle must not touch
them.

**F2d must land before F3d** because `BasicComposable` today requires
`tree: ast.Module` and production-adjacent code reads `.tree` directly:

| Reader | Area | F0b classification target |
|--------|------|---------------------------|
| `emit`, `bind`, `to_executable_ast`, specialization | `model/basic.py` | slow-path or refactor |
| `_register_lower_template` clone/unparse | `model/basic.py` | remove on success path |
| `ShellIndex.from_tree(composable.tree)` | `builder/graph.py` | **package metadata** |
| `shell_index_with_root_transparency(piece.tree)` | `builder/handles.py` | **package metadata** |
| `root.tree` / `source.tree` fallback paths | `assembler/scope.py` | fallback only |
| cache metadata dump | `cache.py` | slow-path / debug |

**F2d implementation choices (pick in F2d design note):**

- Split storage: native-backed composable holds package snapshot + optional
  cached `_artifact_tree`; `.tree` property triggers `copy_python_ast` once; or
- Tree provider protocol on `BasicComposable` with explicit `get_tree_slow_path()`.

Builder shell-index and ref-path checks route through **lower template /
package_v2 metadata**, not eager `.tree` at compile.

### C. Native handle lifetime

Unchanged recommended model: composable stores snapshots + `LowerTemplateBinding`;
scope owns `engine_create` + `NativeTemplateCache`; no composable-owned engine
without close protocol. Document in F2d/F3a.

**Runtime invariants (F0c / F0b — not separate phases):**

- **PyO3 / external slots:** `engine_close` / scope teardown and facade
  finalizers must drop Rust-held `PyObject` references for external overlay
  values; no reference cycles across facade ↔ engine handle. F0b may add an
  optional stress loop (e.g. repeated materialize) with flat Python heap as a
  manual gate, not a hard CI timing assertion.
- **Threading:** With GIL held (§H), handles are still used from multiple
  Python threads in real apps. Document whether each handle type is
  thread-confined (one scope per thread) or internally synchronized; no unsynced
  global template cache. Assert in F0c design note + focused test if shared
  caches exist.

### D. External literal ABI (F1a — current parity only)

F1a matches **`value_to_ast` / `validate_external_value` today**, not an expanded
public surface.

| Supported (F1a parity) | Rejected (explicit tests) |
|------------------------|---------------------------|
| `None`, `bool`, `int`, `float`, `str` | `bytes`, `set`, `frozenset`, `complex`, arbitrary objects |
| `tuple`, `list`, `dict` | dict keys: any key passing `validate_external_value` and hashable as Python dict key (not “string keys only”) |

Adding `bytes` / `set` / `frozenset` is a **separate API change**, not this plan.

F1a picks on-wire form (normalized primitives vs expression text). F1b removes
`ast.unparse(value_to_ast(...))` using that ABI.

### E. `convert_module_artifact` / S9

One `convert_module_artifact` per native scope materialize. Helper conversions
(workspace copy, `to_source`, reprojection) are slow-path only (F5).

### F. Performance baselines (F0b)

Record before swaps:

| Bucket | Metric |
|--------|--------|
| Wall | `import_wall`, `total` |
| Astichi | `harvest`, `materialize_ast`, lower seconds |
| Native | `native_scope_batch_*`, `native_materialize_*` |
| Handoff | `copy_python_ast` count **and** time (separate from `fix_missing_locations`) |
| Post-handoff | `fix_missing_locations` count/time (allowed; tracked separately) |
| Forbidden | `rebuild_composable`, `python_scope_mirror_replay`, per-edge scope apply |
| Non-Astichi | YIDL edge/contribution seconds |

**&lt;0.15s** aspirational only after “Astichi slice” bucket defined in F0b.

### G. Release and selection

- Wheels: advertise `full_lower_engine` **and** self-native capabilities as slices
  land.
- sdist / no native build: clean failure for self-native; `engine=python` valid.
- F5 updates `EngineSelectionContract.md`.

### H. GIL release (out of scope)

Current capabilities report `materialization_releases_gil=false`. **GIL-free
native transform is not a gate for this plan.** Optional later track; do not
block F4e on it.

## API swap map

| # | Today | Target | Blocked by |
|---|--------|--------|------------|
| S1 | `compile` → `ast.parse` + gates | Native extract + gates | F3a–F3d, **F2d** |
| S2 | `register_*_direct(..., tree=tree)` | Snapshot only | F3d |
| S3 | unparse rebind | Native bind | F2a |
| S4 | reproject unparse loop | Native reproject | F2c |
| S5 | mirror replay | commit-only | F1b, F0c capability |
| S6 | Python materialize fallback | native only | F4a–F4d, F0c capability |
| S7 | `ast.unparse` literals | F1a ABI | F1a, F1b |
| S8 | full `materialize_composable` | `copy_python_ast` | F4e |
| S9 | extra convert on helpers | slow-path only | F4e, F5 |
| S10 | eager `tree` at compile | F2d provider + slow `.tree` | **F2d**, F3d |

## Definition of done

### Behavioral

- Self-native production path: goldens + YIDL lifecycle unchanged.
- Public APIs callable; slow paths counted.
- `engine=python` oracle unchanged.

### Production-path guards

Requires **`native.self_native.current_surfaces.v1`** (not hybrid-native alone):

| Guard | Production |
|-------|------------|
| `ast.parse` from `astichi.compile` | 0 |
| `rebuild_composable` | 0 |
| `python_scope_mirror_replay` | 0 |
| full Python `materialize_composable` | 0 |
| per-edge `assembly_scope_apply` | 0 |
| `copy_python_ast` | ~once per lifecycle class materialize |
| `fix_missing_locations` | allowed; separate counter |
| `slow_path_*` | 0 on lifecycle import hot path |

## Phases (roll-build slices)

### F0c — Self-native capability contract (before F1)

- Add capability family in `capabilities.rs`; wire selection + diagnostics.
- Tests: hybrid capabilities without self-native → explicit failure or auto
  fallback per §A.1 policy.
- Document §C runtime invariants (PyO3 cleanup, handle threading).
- Tag: `perf-native-full/f0c-capabilities`

### F0a — Production-path counter guards

- Scoped fixture; assert self-native capabilities + forbidden counters.
- Do not patch global `ast.parse` for entire suite.
- Tag: `perf-native-full/f0a-guards`

### F0b — Leak inventory + baseline

- Inventory **all** `.tree`, `ast.parse`, `ast.unparse` readers in:
  `model/basic.py`, `assembler/scope.py`, `builder/graph.py`,
  `builder/handles.py`, `hygiene/`, `cache.py`, `materialize/api.py`,
  `frontend/api.py` — tag production / slow-path / fallback / test-debug.
- Baseline table per §F.
- Tag: `perf-native-full/f0b-baseline`

### F1a — External literal ABI (current parity only)

- Spec §D; parity tests vs `value_to_ast` / `validate_external_value`.
- Tag: `perf-native-full/f1a-literal-abi`

### F1b — Scope literals + no mirror (S7, S5)

- Literal map per F1a; `scope_no_mirror_replay` capability.
- Tag: `perf-native-full/f1b-scope-literals`

### F2a — Native bind (S3)

- Tag: `perf-native-full/f2a-native-bind`

### F2b — Native bind_identifier

- Tag: `perf-native-full/f2b-native-bind-identifier`

### F2c — Keep-names + reprojection (S4)

- Tag: `perf-native-full/f2c-native-keep-reproject`

### F2d — Facade storage split (before F3)

- Implement §B: tree provider / cached artifact; builder uses package metadata
  for shell-index/ref-path; F0b classifications resolved.
- No `ast.parse` removal in this slice.
- Tag: `perf-native-full/f2d-facade-storage`

### F3a — Compile ledger + parser policy

- Full §A table + §A.1 policy + test/golden map per row.
- Tag: `perf-native-full/f3a-compile-ledger`

### F3b — Native compile validators + name/ports

- All F3a rows including mandatory name analysis and port extraction.
- Tag: `perf-native-full/f3b-compile-validators`

### F3c — Compile differential oracle

- Native vs `engine=python`: same pass/fail class; diagnostics per §A.1
  (strict metadata, loose message).
- Tag: `perf-native-full/f3c-compile-oracle`

### F3d — Compile cutover (S1, S2)

- Requires F2d + `no_python_parse_compile` capability.
- No `ast.parse` on success path; register from snapshot only.
- Tag: `perf-native-full/f3d-compile-swap`

### F4a — Native materialize gates

- Tag: `perf-native-full/f4a-native-gates`

### F4b — Native hygiene parity

- Scope/collision goldens plus **differential** cases for CPython scoping quirks:
  walrus (`:=`) inside nested comprehensions; walrus vs parameter holes /
  keep-names; nested helpers with overlapping names and outer-bound imports.
- Tag: `perf-native-full/f4b-native-hygiene`

### F4c — Materialization surfaces (explicit list)

No indirection through P6c prose — implement and golden each:

| Surface | Golden / test anchor |
|---------|-------------------|
| Expression inserts | existing materialization goldens |
| Block inserts | ditto |
| Parameter holes + parameter payloads | ditto |
| Call-argument payloads (incl. named variadic / directive placeholders) | ditto |
| Elif clause insertion | ditto |
| Identifier overlays | ditto |
| External literal overlays | F1a/F1b + materialize goldens |
| `astichi_ref` literal/method lowering | ditto |
| Managed imports + pyimport collision hygiene | ditto |
| Comments + `emit_commented` policy | ditto or add canonical golden |
| Defaulted / fallback block holes | ditto |
| Unroll rows visible in package/materialization snapshots | structural snapshots |

Add canonical golden where coverage missing before tagging F4c complete.

**F4c equivalence rule:** for each surface row, run **both** `engine=python` and
self-native on the same fixture; assert structural snapshot and/or unparsed
source parity (oracle already defines expected output).

Tag: `perf-native-full/f4c-native-surfaces`

### F4d — `scope.build` native-only (S6)

- `materialize_no_python_fallback` capability.
- Tag: `perf-native-full/f4d-native-build`

### F4e — Handoff (S8, S9)

- `copy_python_ast` + `fix_missing_locations` (separate counters).
- Tag: `perf-native-full/f4e-handoff-swap`

### F5 — Closeout

- §B slow-path counters; docs; §G release.
- Grep guard: production modules in F0b inventory list; `# slow-path` required;
  tests/debug exempt per inventory.
- Self-native CI baseline script.
- Tag: `perf-native-full/f5-closeout`

### F6 — Handoff perf (optional)

- Primary: bulk PyO3 emit.
- Emergency: `ast.parse` at boundary = **alternate artifact policy** (document
  if used; may erase F3d win).
- Tag: `perf-native-full/f6-handoff-perf`

## What stays Python

| Item | Why |
|------|-----|
| External binding values | Object identity |
| Exception formatting | UX |
| `engine=python` | Oracle |
| Public slow paths | Counted |
| `fix_missing_locations` | Public contract; separate counter |

## Non-goals

- Expanding external literal types (`bytes`/`set`/…) in this track.
- YIDL bulk engine / lifecycle precompiled module.
- Private CPython compiler APIs as boundary.
- GIL-free materialization (§H).
- Removing Python reference engine.

## Stop conditions

- Ledger row / F4c surface without parity → waiver + oracle.
- F4e without F0b bucket movement → stop F6; document YIDL vs copy vs exec.
- Emergency boundary `ast.parse` → update artifact policy + counters.

## Relation to other docs

| Document | Role |
|----------|------|
| `NativePerformancePlan.md` | Hybrid-era incremental track; P7 goals superseded here for full-native |
| `NativeLowerEngineDetailedPlan.md` | Engine feature completeness |
| **This plan** | Self-native boundary + slices |
| `EngineSelectionContract.md` | Selection + capabilities (extend in F0c) |

## Quick verification

```bash
cd astichi
uv run pytest -q
uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q
# After F0c/F0a: require self-native capabilities in fixture
ASTICHI_LOWER_ENGINE=native uv run --with frozendict python \
  docs/validation/perf/yidl_lifecycle_import_baseline.py \
  --engine native --require-native-counters
uv run pytest tests/test_native_success_path_guards.py -q
```
