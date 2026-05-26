# Performance Validation

This directory contains repeatable performance probes for Astichi development.
The scripts are validation tools, not supported product APIs, and should keep
wall-time assertions out of the normal unit test suite.

Use these probes to capture phase timing, call counts, and profiler data before
and after performance work. Cache outputs and profiler dumps belong in local
scratch directories and should not be committed.

The YIDL split dataclass probe needs YIDL's parser dependency. From this repo,
run it with:

```bash
uv run --with lark python docs/validation/perf/yidl_split_dataclass_profile.py --skip-runtime
```

The YIDL lifecycle import baseline records phase timings, Astichi's opt-in
counters, and YIDL assembly-runtime counters for the 8-class decorator
workload. The YIDL counters separate edge traversal, contribution selection,
no-match contribution checks, and contribution application from Astichi lower
candidate lookup/materialization:

```bash
uv run --with frozendict python docs/validation/perf/yidl_lifecycle_import_baseline.py
```

Pass `--engine python`, `--engine auto`, or `--engine native` to compare lower
engine routes. Use `--require-native-counters` with `--engine native` when a
checkpoint must prove the native scope path was exercised.

Native scope batch apply quarantines Python lower-state mirror replay by
default. Set `ASTICHI_NATIVE_SCOPE_MIRROR_REPLAY=1` to restore the compatibility
slow path (counter `python_scope_mirror_replay`).

The generated-AST cache probe exercises the opt-in builder cache and reports
cold, warm in-process, warm disk, unparse, and compile timings:

```bash
uv run python docs/validation/perf/generated_ast_cache_profile.py
```
