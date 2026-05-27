# Full Self-Native Rust AST Plan

Status: **canonical roll-build plan** (F0 sign-off recorded 2026-05-27).

**This document is the only active implementation plan for the full-native
boundary.** Everything else under `dev-docs/perf-refactor/` except this file and
`README.md` is **historical context** (probe results, hybrid-era slices, old
P0–P7 tracks). Do not start new work from those docs.

Tags: `rust-fsn/*`.

Scratch reviews: `astichi/scratch/FullSelfNativeRustAstPlan-Review*.md`.

## F0 sign-off (agreed)

- [x] This plan is the isolated, canonical roll-build for full self-native.
- [x] Goal: **pure native** on the production path; **delete** hybrid Python AST
  work, do not preserve it as a counted “slow path.”
- [x] Behavior: **identical** to today’s correct output (goldens + lifecycle);
  fix **obvious bugs** when native/oracle diff exposes them; `engine=python`
  remains differential oracle only.
- [x] §A.1 parser policy: **`auto`** may fall back to Python parse on rustpython
  grammar mismatch (with `native_parser_grammar_fallback` counter +
  `EngineSelectionEvent`); **explicit `native`** fails clearly on mismatch.
- [x] Public APIs (`.tree`, `emit`, `describe`, etc.) stay callable; production
  implements them via **native projection**, not Python re-parse/materialize.
- [x] §C handle model: composable snapshots + scope-owned engine +
  `NativeTemplateCache`.
- [x] §D literals: current `value_to_ast` parity only.
- [x] §H: GIL-free materialize out of scope for this roll.
- [x] F0b inventory + baseline table committed before F3d.
- [x] First tags: **F0c** → **F0b** → F1a…

## Thesis

Hybrid native already proved the engine. The remaining work is **not hard
algorithm** work: stop duplicating Python `ast` on the success path (parse,
unparse, `materialize_composable`, mirror replay, eager `.tree`). Rust already
owns parse, package-v2, batch, and materialize IR — wire the facade to use it
end-to-end and copy CPython `ast` **once** at handoff.

## Target boundary

```text
Production (self_native.current_surfaces.v1):
  compile / bind / scope.build / to_executable_ast
    -> thin Python facade (external values, exceptions)
    -> Rust: parse, validate, package, scope, materialize, hygiene
    -> copy_python_ast  (only mandatory CPython ast construction)
    -> ast.fix_missing_locations
    -> caller compile / exec

Not on production path (delete or test-only):
  ast.parse in compile, ast.unparse loops, Python materialize_composable,
  mirror replay, Python lower fallback, per-edge Python scope apply,
  eager composable.tree for builder/shell-index
```

**Oracle:** `engine=python` for differential tests until a row is native-proven,
then native becomes authoritative.

## Self-native capabilities

Coarse `native.full_lower_engine.current_surfaces.v1` is insufficient. Advertise
per slice; production lifecycle requires **`native.self_native.current_surfaces.v1`**.

| Capability | Slice |
|------------|-------|
| `native.self_native.compile_validation.v1` | F3b–c |
| `native.self_native.no_python_parse_compile.v1` | F3d |
| `native.self_native.literal_payload_abi.v1` | F1b |
| `native.self_native.scope_no_mirror_replay.v1` | F1b |
| `native.self_native.materialize_no_python_fallback.v1` | F4d |
| `native.self_native.current_surfaces.v1` | F4c + F4e |

Selection: `auto` uses hybrid only until self-native caps exist; then self-native.
Explicit `native` without self-native caps → diagnostic (no silent hybrid).

## Correctness rule

- **Pass:** structural goldens, materialization goldens, YIDL/lifecycle tests,
  F3c/F4c native-vs-python differential on same fixtures.
- **Fix:** if diff shows an obvious bug (wrong output, not wording), fix in
  native and update golden with justification.
- **Do not** preserve hybrid shortcuts that contradict oracle unless documented
  as intentional waiver (rare).

## Contracts (implementation detail)

### Compile parity (F3a–d)

Full ledger in F3a (all `frontend/api.py` gates, padding, `source_kind`,
`keep_names`, `arg_names`, attach source file, parser matrix). Name analysis and
port extraction are **native in F3b**, not Python projection.

**F3c diagnostics:** strict type/filename/line/offset; loose message (regex).

### Facade storage (F2d, before F3d)

- No eager `tree: ast.Module` on compile for self-native composables.
- **Builder** (`graph.py`, `handles.py`): shell-index / ref-path from **package
  metadata**, not `.tree`.
- **`.tree` / `emit` / `describe` / `inventory`:** native-backed projection when
  called (tests, tooling, debug) — not a second Python lower pipeline.
- Delete `_register_lower_template` unparse path on success route.

### Handles (§C)

Composable: snapshots + `LowerTemplateBinding`. Scope: one engine +
`NativeTemplateCache`. PyO3 external slots dropped on close. Threading documented
in F0c (thread-confined scope or synchronized cache).

### Literals (F1a–b)

Current `value_to_ast` / `validate_external_value` types only. Native literal map
without `ast.unparse(value_to_ast(...))`.

### Handoff (F4e)

One `convert_module_artifact` per materialized module. No extra converts on
production helpers; debug `to_source` / workspace copy only in tests if still
needed.

### F0b baseline

Record lifecycle import metrics before swaps (wall, counters, forbidden paths,
`copy_python_ast` vs `fix_missing_locations`, YIDL bucket). Aspirational speedup
documented after F0b defines “Astichi slice.”

## API swaps (delete hybrid code)

| # | Remove from success path |
|---|-------------------------|
| S1 | `ast.parse` in `compile` |
| S2 | Python `tree` required for native register |
| S3–S4 | `ast.unparse` rebind / reproject |
| S5 | mirror replay + Python lower mirror state |
| S6 | Python `materialize_composable` / builder merge fallback |
| S7 | `ast.unparse` external literals |
| S8 | full Python hygiene in `to_executable_ast` |
| S9 | extra `convert_module_artifact` before final handoff |
| S10 | eager `.tree` for production builder/compile |

## Production guards (lifecycle import)

With `self_native.current_surfaces.v1`:

| Must be zero | Notes |
|--------------|-------|
| `ast.parse` from compile | |
| `rebuild_composable` | |
| `python_scope_mirror_replay` | |
| Python `materialize_composable` | |
| per-edge `assembly_scope_apply` | batch only |
| hybrid fallback without counter | grammar fallback counted if used |

| Required | Notes |
|----------|-------|
| `copy_python_ast` | ~once per class materialize |
| `native_scope_batch_*`, `native_materialize_*` | |

## Phases

Roll-build tags; each leaves tests green. Prefer **deleting** dead hybrid code in
the slice that makes it unreachable.

### F0c — Capabilities + selection + threading note

Tag: `rust-fsn/f0c-capabilities`

Threading: `FullSelfNativeRustAstPlan-F0c-threading.md`.

### F0a — Scoped production-path guard tests

Tag: `rust-fsn/f0a-guards`

### F0b — Leak inventory (classify: delete vs test-only) + baseline table

Appendix: `FullSelfNativeRustAstPlan-F0b-inventory.md`.

Tag: `rust-fsn/f0b-baseline`

### F1a — Literal ABI spec + parity tests

Tag: `rust-fsn/f1a-literal-abi`

### F1b — Native literals + no mirror replay

Tag: `rust-fsn/f1b-scope-literals`

### F2a–c — Native bind / bind_identifier / keep / reproject

Tags: `rust-fsn/f2a-native-bind`, `f2b-native-bind-identifier`,
`f2c-native-keep-reproject`

### F2d — Facade storage: package metadata for builder; no eager tree

Tag: `rust-fsn/f2d-facade-storage`

### F3a — Compile ledger + test map

Tag: `rust-fsn/f3a-compile-ledger`

Ledger: `FullSelfNativeRustAstPlan-F3a-compile-ledger.md`.

### F3b — Native validators + native name/ports

Tag: `rust-fsn/f3b-compile-validators`

### F3b — Native validators + native name/ports

Tag: `rust-fsn/f3b-compile-validators`

### F3c — Differential oracle vs python engine

Tag: `rust-fsn/f3c-compile-oracle`

### F3d — Remove `ast.parse` on compile success path

Tag: `rust-fsn/f3d-compile-swap`

### F4a — Native materialize gates

Tag: `rust-fsn/f4a-native-gates`

### F4b — Native hygiene (+ walrus/comprehension differential cases)

Tag: `rust-fsn/f4b-native-hygiene`

### F4c — All materialization surfaces (native vs python differential each)

Expression/block/parameter/call-arg/elif overlays, external literals, ref
lowering, managed imports/pyimport, comments/`emit_commented`, defaulted holes,
unroll snapshot rows.

Tag: `rust-fsn/f4c-native-surfaces`

### F4d — `scope.build` native-only

Tag: `rust-fsn/f4d-native-build`

### F4e — `to_executable_ast` = handoff only

Tag: `rust-fsn/f4e-handoff-swap`

### F5 — Delete unreachable hybrid code; README boundary; CI counters

Tag: `rust-fsn/f5-closeout`

### F6 — Optional: cheaper `copy_python_ast` if F0b shows dominance

Emergency boundary `ast.parse` is a **different policy** — only with explicit
sign-off. Tag: `rust-fsn/f6-handoff-perf`

## What stays Python (minimal)

| Item | Why |
|------|-----|
| External binding object identity | PyO3 slots |
| User-facing exceptions | UX |
| `engine=python` | Oracle |
| `fix_missing_locations` | Cheap post-handoff |
| `copy_python_ast` | Public `ast.Module` contract |

## Non-goals

- Literal type expansion (`bytes`/`set`/…).
- YIDL bulk / lifecycle precompile (separate).
- GIL-free materialize (§H).
- Preserving hybrid success-path code “just in case.”

## Historical docs

Do not execute from: `NativePerformancePlan.md`, `NativeLowerEngineDetailedPlan.md`,
`SlicedBuildPlan.md`, `RemainingRollBuildPlan.md`, etc. Consult only for
background or grep of old decisions. **Implement from this file.**

## Verification

```bash
cd astichi
uv run pytest -q
uv run python tests/versioned_test_harness.py run-tests-all --pytest-args -q
ASTICHI_LOWER_ENGINE=native uv run --with frozendict python \
  docs/validation/perf/yidl_lifecycle_import_baseline.py \
  --engine native --require-native-counters
```
