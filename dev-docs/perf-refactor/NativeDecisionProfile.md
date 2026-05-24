# Native Decision Profile

Status: Slice 14a decision record; superseded as a stop gate by
`NativeLowerEngineDetailedPlan.md`.

Date: 2026-05-25

## Decision

The original Slice 14a decision was to avoid starting the full native
lower-engine implementation from the then-current profile alone. That profile
remains useful context, but it is no longer the controlling implementation
gate.

The current requirement is to build a fully functional native lower engine.
`NativeLowerEngineDetailedPlan.md` is the source of truth for that required
roll-build.

At the time of this profile, the Python lower engine covered the YIDL lifecycle
hot path without the legacy builder adapter counters, but the remaining miss
was mostly outside the Astichi lower tables. That made the profile a weak
standalone reason to start native work, but it did not disprove the native
architecture.

The risk called out by this profile still matters: native parser speed alone is
not enough. The native implementation must move the whole lower-engine success
path, including template extraction, candidate lookup, overlays,
materialization, hygiene, and artifact copy, behind the native boundary.

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

## Historical Native Backend Direction

The original direction from this profile was:

- Rust/PyO3 remains the current evidence-backed probe choice;
- parser/IR-backed template registration is viable;
- public CPython `ast`/`_ast` plus `compile(...)` remains the artifact boundary;
- no internal CPython compiler API is justified by this profile;
- engine selection must remain coarse and capability-gated.

The updated implementation direction is:

- use the Rust/PyO3 native probe result as the production parser/IR starting
  point;
- build the full lower engine natively, not only parser/artifact construction;
- select native only when the extension declares the full lower-engine
  capability set.

## Historical Follow-Up Gate

The original stop-gate guidance was to rerun this decision before starting
`15a` after one of these changes:

- YIDL edge traversal/contribution application is collapsed, cached, or moved
  behind a bulk plan;
- the import profile shows `candidate_lookup_lower`, occurrence/index updates,
  materialization-plan construction, hygiene, rebuild, or artifact construction
  as the dominant remaining cost;
- a native prototype can execute a full lower table/materialization operation
  stream and show a workload-level win, not only a parser microbenchmark.

That stop gate is superseded. The native roll-build may proceed, but the first
native slice must ensure that a loadable skeleton is not selected as a usable
native lower engine without the full capability gate.
