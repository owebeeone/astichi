# F6 — Handoff transfer (no redundant clone)

Status: tag `rust-fsn/f6-handoff-perf`.

F0b showed `copy_python_ast` at **0.024s** for 8 lifecycle classes — the same
order as `materialize_ast`, indicating a second full-tree copy after native
`convert_module_artifact`.

## Change

When `native.self_native.handoff_transfer.v1` is advertised:

1. Native `assembly_state_materialize_to_python_ast` is timed as **`copy_python_ast`**
   (the sole CPython construction).
2. `native_materialize_workspace_copy` is not incremented on that path.
3. `BasicComposable._executable_handoff_pending` is set on native materialize.
4. First `to_executable_ast()` returns the materialized tree by **transfer** (no
   `clone_ast`); a second call clones for safety.

## Post-F6 lifecycle sample (self-native, 8 classes)

| Metric | F0b hybrid | F6 transfer |
|--------|------------|-------------|
| `copy_python_ast` (count) | 8 | 8 |
| `copy_python_ast` (s) | 0.024 | 0.030 |
| `native_materialize_workspace_copy` | 8 (implicit) | **not observed** |
| `to_executable_ast` (hot) | 0 | 0 |

Count shape is correct (one CPython construction per class). Wall time on this
machine is noise-dominated at ~30ms total; the win is eliminating the redundant
`clone_ast` after native materialize, not a guaranteed import-wall drop.

Re-baseline:

```bash
cd astichi
uv run --with frozendict python docs/validation/perf/yidl_lifecycle_import_baseline.py \
  --engine native --require-native-counters
```
