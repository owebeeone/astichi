# F0b — Hybrid leak inventory and lifecycle baseline

Status: recorded at tag `rust-fsn/f0b-baseline` on branch `rust-fsn`.

Environment: Astichi dev checkout, built `_astichi_native_engine`, Python 3.12,
`ASTICHI_LOWER_ENGINE=native`, module `pyrolyze.runtime.context_lcm`, 8 decorated
lifecycle classes.

Command:

```bash
cd astichi
uv run --with frozendict python docs/validation/perf/yidl_lifecycle_import_baseline.py \
  --engine native --require-native-counters
```

## Baseline table (hybrid native, pre–self-native)

| Metric | Value |
|--------|------:|
| `import_wall` (s) | 0.428 |
| `assembly` (s) | 0.290 |
| `materialize_ast` (s) | 0.024 |
| `compile_exec_ast` (s) | 0.008 |
| `native_scope_batch_size` | 1659 |
| `native_scope_batch_native_only` | 1659 |
| `native_scope_batch` (count) | 591 |
| `copy_python_ast` (count) | 8 |
| `copy_python_ast` (s) | 0.024 |
| `rebuild_composable` | 0 |
| `assembly_scope_apply` | 0 |
| `python_scope_mirror_replay` | 0 |
| `materialize_composable` (counter) | not observed on import path |
| `to_executable_ast` (hot counter) | 0 |
| Selected engine | `native-rust` (hybrid tier) |
| Self-native production gate | **not satisfied** (`native.self_native.current_surfaces.v1` absent) |

YIDL runtime (import path): `edge_calls` 904, `contribution_apply_calls` 591,
`contribution_select_calls` 721 — dominated by YIDL assembly, not Astichi parse.

## Leak inventory (classify: delete on success path vs test/oracle/slow)

| ID | Location | Mechanism | Baseline on lifecycle import | Slice | Disposition |
|----|----------|-----------|------------------------------|-------|-------------|
| L1 | `frontend/api.py` `compile` | `ast.parse` before native re-parse | compile runs per class (not in counter table) | F3d | **Delete** on production success path |
| L2 | `model/basic.py` `_register_lower_template` | `ast.unparse` + rebind | registration path | F2c | **Delete** on success path |
| L3 | `model/basic.py` `_rebuild_composable` | Python lower rebuild | counter 0 on import | F2d/F4 | **Delete** when native projection owns composable |
| L4 | `model/basic.py` `.tree` / `emit` | eager `clone_ast(self.tree)` | not on hot import counters | F2d | **Slow path** only (native projection); not deleted as API |
| L5 | `assembler/scope.py` mirror replay | Python candidate replay after native batch | counter 0 (`native_scope_batch_native_only` = 1659) | F1b | **Delete** when `scope_no_mirror_replay` cap on |
| L6 | `assembler/scope.py` literals | `ast.unparse(value_to_ast(...))` | overlay registration | F1b | **Delete** on success path |
| L7 | `materialize/api.py` `materialize_composable` | Python materialize | not observed on import | F4d | **Delete** on production `scope.build` |
| L8 | `hygiene/api.py` `to_executable_ast` | `ast.parse(ast.unparse(tree))` | hot counter 0 | F4b/F4e | **Delete**; handoff = `copy_python_ast` + `fix_missing_locations` |
| L9 | `facade` / `convert_module_artifact` | extra CPython ast copies | `copy_python_ast` = 8 (1× per class) | F4e | **Keep one**; delete extras |
| L10 | `emit/api.py` debug compare | `ast.unparse` / `ast.parse` | tooling | — | **Test/debug only** |
| L11 | `lowering/unroll.py` diagnostics | `ast.unparse` in errors | error path | — | **Keep** (diagnostics) |
| L12 | Native `compile` path | duplicate parse (Python then Rust) | implicit in compile wall | F3d | **Delete** Python parse |

## Production guard targets (post F4c/F4e)

When `native.self_native.current_surfaces.v1` is advertised and
`select_self_native_production_engine` selects `native-rust`:

| Counter | F0b hybrid |
|---------|------------|
| `ast.parse` from compile | present (L1) → **0** |
| `rebuild_composable` | 0 → **0** |
| `python_scope_mirror_replay` | 0 → **0** |
| `materialize_composable` | absent → **0** |
| `assembly_scope_apply` (per-edge) | 0 → **0** |
| `copy_python_ast` | 8 → **~8** (once per class materialize) |
| `native_scope_batch_*` | present → **required** |

## Astichi slice speedup (aspirational, post F0b)

F0b defines the measurement harness only. Expected wins after deleting L1/L5/L6/L7/L8
and keeping a single `copy_python_ast` are documented after F4e re-baseline; do not
quote a speedup factor until that run.

## Notes

- Hybrid `select_lower_engine("native")` remains valid for this baseline; production
  guards must use `select_self_native_production_engine` once self-native caps land.
- Grammar fallback (`native_parser_grammar_fallback`) not observed on lifecycle module.
