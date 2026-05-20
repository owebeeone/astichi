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

The generated-AST cache probe exercises the opt-in builder cache and reports
cold, warm in-process, warm disk, unparse, and compile timings:

```bash
uv run python docs/validation/perf/generated_ast_cache_profile.py
```
