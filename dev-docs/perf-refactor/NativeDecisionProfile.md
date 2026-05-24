# Native Decision Profile

Status: Slice 14a decision record.

Date: 2026-05-25

## Decision

Do not start the full native lower-engine implementation checkpoints
`15a`-`16d` from the current profile.

The Python lower engine now covers the YIDL lifecycle hot path without the
legacy builder adapter counters, but the remaining miss is mostly outside the
Astichi lower tables. Native parser/IR work remains technically viable and the
probe should be kept, but the next performance work should first reduce or
restructure YIDL edge traversal/contribution application, then rerun this gate.

Proceeding directly to native table/materialization implementation would add a
second engine before the profile identifies a lower-engine bottleneck large
enough to recover the target.

## Import Profile

Command:

```bash
uv run --with frozendict python docs/validation/perf/yidl_lifecycle_import_baseline.py
```

Representative result:

```text
decorated_classes: 8
import_wall: 0.941 s
total decorator work: 0.866 s
assembly: 0.797 s
materialize_ast: 0.055 s
compile_exec_ast: 0.010 s

Astichi lower counters:
candidate_lookup_lower: 1597 calls, 0.047 s
assembly_scope_apply: 1597 calls, 0.052 s
lower_materialization_plan: 8 calls, 0.006 s
rebuild_composable: 8 calls, 0.060 s
to_executable_ast: 8 calls, 0.055 s

YIDL runtime counters:
edge_calls: 904, 0.341 s
contribution_select_calls: 628, 0.001 s
contribution_apply_calls: 560, 0.325 s
contribution_no_match: 68
empty_resource_noops: 0
```

The old adapter success-path counters remain absent or zero:

```text
build_merge: 0
builder_adapter_mutation: 0
lower_materialization_adapter_fallback: 0
```

## Target Comparison

The original proposal target for YIDL/Astichi decorator work was about
`0.659 s` total, with `0.575 s` assembly and `0.083 s` materialization. The
current materialization number is already under that target. Assembly remains
above target, but the directly measured Astichi lower pieces are materially
smaller than the YIDL edge/contribution runtime envelope.

Approximate lower-bound interpretation:

```text
Astichi lower candidate/apply: about 0.099 s
Astichi plan/rebuild/executable artifact: about 0.121 s
YIDL edge + contribution apply: about 0.666 s
```

Some overlap is expected because YIDL contribution application calls into
Astichi. Even with overlap, the profile does not show a clean native-lower
table bottleneck that can be attacked independently.

## Native Probe Result

Commands:

```bash
uv run python native_probe/native_probe.py verify --json
uv run python native_probe/native_probe.py bench --iterations 200 --json
```

The probe still parses, converts, copies to CPython AST, validates with
`compile(...)`, executes the sample, and handles all current
`tests/data/gold_src/*.py` fixtures without fallback:

```text
fixture_count: 40
fixture_native_compile_ok: 40
fixture_fallback_count: 0
```

Built-in sample, 200 iterations:

```text
source_bytes: 368
native_parse_seconds: 0.0033
artifact_copy_seconds: 0.0064
ast_parse_plus_minimal_scan_seconds: 0.0072
lower_composable_facade_seconds: 0.0048
compile_seconds: 0.0058
```

Fixture-shaped timings, 200 iterations:

```text
lifecycle_template_surfaces.py: native_parse 0.0309 s, artifact_copy 0.0455 s, ast_parse+scan 0.0697 s
pyimport_staged_composition.py: native_parse 0.0050 s, artifact_copy 0.0085 s, ast_parse+scan 0.0109 s
parameter_holes.py: native_parse 0.0216 s, artifact_copy 0.0371 s, ast_parse+scan 0.0459 s
edge_multibind_staged.py: native_parse 0.0105 s, artifact_copy 0.0180 s, ast_parse+scan 0.0222 s
```

The native parser is faster than `ast.parse(...) + minimal scan` on these
fixtures, but not by the 5x threshold from `NativeAstProbe.md`. Artifact copy to
CPython AST is also large enough that parser speed alone is not the deciding
factor.

## Native Backend Direction

Keep the native backend direction as:

- Rust/PyO3 remains the current evidence-backed probe choice;
- parser/IR-backed template registration is viable but not yet
  profile-justified for production routing;
- public CPython `ast`/`_ast` plus `compile(...)` remains the artifact boundary;
- no internal CPython compiler API is justified by this profile;
- engine selection must remain coarse and opt-in until a native run proves a
  workload-level win.

## Follow-Up Gate

Before starting `15a`, rerun this decision after one of these changes:

- YIDL edge traversal/contribution application is collapsed, cached, or moved
  behind a bulk plan;
- the import profile shows `candidate_lookup_lower`, occurrence/index updates,
  materialization-plan construction, hygiene, rebuild, or artifact construction
  as the dominant remaining cost;
- a native prototype can execute a full lower table/materialization operation
  stream and show a workload-level win, not only a parser microbenchmark.

Until then, `14b` and `14c` may proceed only as boundary/skeleton work. They
must not route production behavior to native by default.
