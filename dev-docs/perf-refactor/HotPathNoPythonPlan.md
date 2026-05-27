# Hot path: no Python until libast handoff

Status: **active** (replaces `FullSelfNativeRustAstPlan` as the roll-build to execute).

Tags: `rust-hot/h0`–`h3` done; `rust-hot/h4-production-green` when H4 tests are green.

## Success (fool-proof)

One subprocess, one module, counters only:

```bash
cd astichi
uv run --with frozendict python docs/validation/perf/yidl_lifecycle_import_baseline.py \
  --engine native --require-native-counters
```

When `native.self_native.current_surfaces.v1` is advertised:

| Counter | Required |
|---------|----------|
| `native_compile_parse` | **0** (no `parse_module` / Emitter on compile hot path) |
| `python_compile_ast_parse` | **0** |
| `native_materialize_workspace_copy` | **0** (handoff uses `copy_python_ast` only) |
| `copy_python_ast` | **== `decorated_classes`** (once per class at handoff) |
| `materialize_composable`, `python_scope_mirror_replay`, … | **0** (existing production guards) |

**Test:** `tests/test_lifecycle_hot_path_python_gate.py` — fails until the table is true.

Perfmon / import wall is informational; **counters are the gate**.

## Loop

```text
while test_lifecycle_hot_path_python_gate fails:
    find counter violation (which Py boundary fired)
    remove that call from the hot path (Rust-only)
commit + tag rust-hot/N
```

No slice checklist. No `current_surfaces` until the test passes.

## Phases (small, in order)

### H0 — Gate test + docs (this change)

- Hot-path forbidden counter list + handoff shape asserts.
- Lifecycle subprocess test (expect **red** on current tree).
- Mark `FullSelfNativeRustAstPlan.md` historical in README.

### H1 — Compile without `convert_module_artifact`

- `astichi.compile` registers from native package-v2 only; no CPython `tree` on success.
- Target: `native_compile_parse` → 0 on lifecycle import.

Tag: `rust-hot/h1-compile-rust-only`

### H2 — Snapshots without `PyDict` on success path

- Scope/batch consume Rust handles; Python dict snapshots debug-only.

Tag: `rust-hot/h2-no-pydict-snapshots`

### H3 — Single handoff

- Only `assembly_state_materialize_to_python_ast` (or successor) opens Py gate; `copy_python_ast` count == classes.

Tag: `rust-hot/h3-handoff-only`

### H4 — Revoke false `current_surfaces` meaning

- `REQUIRED_SELF_NATIVE_PRODUCTION_FEATURES` is the full `SELF_NATIVE_SLICE_FEATURES`
  tuple (capstone + every slice flag), not the capstone alone.
- Lifecycle/compile/scope use `select_effective_lower_engine` /
  `select_self_native_production_engine` for production; hybrid
  `select_lower_engine` stays for coarse/matrix checks.
- `tests/test_hot_path_h4_production_green.py` + `assert_self_native_production_green`.

Tag: `rust-hot/h4-production-green`

### O3 — Production compile (no matrix re-parse)

- ``o3_production_hot_path_compile_active()``: same placeholder path as the
  lifecycle gate when self-native production is selected and
  ``ASTICHI_LOWER_ENGINE_MATRIX`` is unset (real import / lifecycle).
- Pytest matrix sets ``ASTICHI_LOWER_ENGINE_MATRIX=1`` so ``[native]`` tests
  still parse for marker/oracle coverage.

Tag: `rust-hot/o3-production-compile`

## Non-goals

- Wrapper `.so` interposer (optional later; counters first).
- Removing final `_ast` handoff (lifecycle still uses `compile(ast.Module)`).
