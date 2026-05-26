# Native Performance Roll-Build Plan

Status: ready for roll-build planning.

This plan starts after the native lower-engine path is functionally selectable
by default. At this point native correctness is proven for the current Astichi
suite, but the performance result is still negative because the default native
path is hybrid: Python builds and rebuilds much of the lower metadata, then the
native engine mirrors part of the same state and answers some scope queries.

The goal of this plan is to remove Python success-path work, not to add more
native mirrors around it.

## Current Baseline

The current local profile for `pyrolyze.runtime.context_lcm` is:

| Mode | Wall time | Meaning |
| --- | ---: | --- |
| `ASTICHI_LOWER_ENGINE=python` | about 1.9-2.0s | Python lower path only |
| default `auto` selecting native | about 2.4s | native hooks active, but hybrid |

Native counters prove the native path is active:

- `native_candidate_query_composable`
- `native_candidate_query_external`
- `native_candidate_query_identifier`
- `native_scope_append_edge`
- `native_scope_append_occurrence`
- `native_scope_append_overlay`
- `native_scope_mark_satisfied`

The remaining Python hot counters still explain the regression:

- `rebuild_composable`
- `candidate_lookup_lower`
- `assembly_scope_apply`
- `to_executable_ast`

Performance work is not complete until native mode reduces those Python hot
counters or moves them to explicitly named slow/debug paths.

## Performance Target

Use these targets for planning. Do not encode them as brittle unit-test timing
thresholds.

| Result | `context_lcm` target | Notes |
| --- | ---: | --- |
| acceptable | <= forced Python | native no longer regresses |
| good | about 1.2s | most duplicate Python lower work removed |
| strong | 0.8-1.0s | native compile, specialization, scope, and materialization own the hot path |
| stretch | 0.5-0.7s | requires YIDL/import/startup/final artifact costs to also be tight |

## Roll-Build Rules For This Plan

- Start from a clean `astichi/` tree.
- Suggested start tag: `perf-native/start`.
- Suggested checkpoint tag prefix: `perf-native/`.
- Commit and tag each phase only after its focused verification and the full
  Astichi suite pass.
- Do not commit machine-local timing logs. Put raw timing/profiler artifacts in
  ignored scratch space and summarize only stable conclusions in commit
  messages or follow-up docs.
- Every phase must preserve the canonical golden/snapshot success path. Bespoke
  tests should cover narrow mechanics, diagnostics, counters, and adapter
  behavior only.
- Stop if a phase requires changing Astichi source semantics merely to make the
  native path faster. Patch the design first.
- Stop if native cannot represent a lower-layer fact without asking Python to
  reconstruct inventory on the hot path.

## Required Benchmark Command Shape

Run the workload from a parent checkout that has Astichi, YIDL, YIDL lifecycle,
and Pyrolyze available. Use relative paths from that checkout, not machine
absolute paths.

Example command shape:

```bash
PYTHONPATH="pyrolyze/src:yidl-lifecycle/src:yidl/src:astichi/src" \
  .venv/bin/python pyrolyze/src/pyrolyze/runtime/context_lcm.py
```

For counter runs, wrap the script with `astichi.perf_counters.collect_perf_counters`
and print:

- selected lower engine snapshot;
- wall time;
- `native_*` counters;
- top Python counter counts;
- top Python counter seconds.

The committed harness for this plan is:

```bash
uv run --with frozendict python \
  docs/validation/perf/yidl_lifecycle_import_baseline.py --engine native \
  --require-native-counters
```

Use `--engine python`, `--engine auto`, and `--engine native` for comparative
runs. The harness reports `selected_lower_engine`, full Astichi counters,
native counter summaries, and top Python hot counters as JSON.

The benchmark gate for each phase is comparative:

- forced Python;
- default `auto`;
- explicit `ASTICHI_LOWER_ENGINE=native`, if different from `auto`.

## Phase P0: Benchmark Harness And Baseline

Goal: make performance measurement repeatable enough that each following phase
can prove movement.

Work:

- Add a small benchmark helper or pytest utility that runs the lifecycle import
  workload with Astichi counters enabled.
- The helper should accept engine selection: `python`, `auto`, and `native`.
- Print machine-readable counts and times for the hot counters listed above.
- Keep raw timings out of committed assertions.
- Document the command in this file if the helper name differs from the command
  shape above.

Acceptance:

- Focused benchmark helper runs for forced Python and native-selected mode.
- The helper reports `select_lower_engine()` output.
- Native mode reports at least one `native_*` counter.
- Full Astichi suite passes.

Expected performance movement:

- None required. This is the measurement checkpoint.

Tag after success: `perf-native/p0-baseline`.

Stop if:

- The workload cannot be run repeatably from the workspace without absolute
  machine paths.
- Counter collection changes runtime behavior or hides failures.

## Phase P1: Native-Authoritative Facade Contract

Goal: make the Python facade capable of representing a native-owned lower
template without requiring Python `Inventory` and Python lower-template objects
on the success path.

Work:

- Introduce an explicit native-backed composable facade or extend the existing
  facade with a native-owned lower package attachment.
- The native binding must carry source/origin, native template handle or
  package handle, and enough debug projection hooks for existing diagnostics.
- Keep public `emit`, `materialize`, `describe`, and structural snapshot APIs
  available, but allow them to call explicit slow-path projections.
- Do not remove the Python reference engine.
- Keep the current Python projection rows as compatibility data until native
  package-v2 parity covers all rows needed by Python materialization and
  diagnostics. This guard prevents P1 from regressing the lifecycle workload
  by swapping in incomplete native projection rows too early.
- Do not make Python `inventory` construction part of the native-owned package
  contract; P2 owns removing it from native-selected `compile(...)`.

Acceptance:

- Native-selected compile returns a facade with native source/origin, a native
  structural snapshot, and a native package-v2 snapshot.
- Python-selected compile is unchanged.
- Existing public diagnostics still have a projection path.
- Focused facade/template tests pass.
- The lifecycle benchmark still reports native counters without introducing
  builder-adapter fallback on the native route.
- Full Astichi suite passes.

Expected performance movement:

- Small or neutral until P2 routes compile through it.

Tag after success: `perf-native/p1-facade`.

Stop if:

- Existing public APIs require eagerly materialized Python inventory in ways
  that cannot be made explicit slow paths.
- The facade boundary would make native and Python semantics diverge.

## Phase P2a: Native Package-V2 Parity For Current Surfaces

Goal: make native package-v2 extraction match the Python lower package oracle
for the lifecycle/YIDL marker shapes before any facade projection cutover.

Work:

- Add focused parity fixtures for current lifecycle-heavy surfaces:
  `__astichi_arg__` definitional markers, `__astichi_arg__` identifier sites,
  call keyword-name identifier sites, `astichi_ref(external=...)`, imports,
  holes, and compact YIDL-like mixed templates.
- Fix native generic marker extraction so marker ids, source order, AST paths,
  statement paths, marker kinds, operation keys, resource names, and flags match
  Python `recognize_markers(...)` package rows.
- Fix typed native rows that depend on generic marker ids: pyimport, comment,
  ref, unroll, and managed import rows.
- Keep the Python facade projection unchanged in this phase. This phase proves
  native package data is complete enough to become authoritative later.

Acceptance:

- Native package-v2 snapshots match the Python oracle for the new parity
  fixtures and the existing package-v2 fixtures.
- Native source registration stores the same package rows for those fixtures.
- Focused native package-v2 tests pass after rebuilding the native extension.
- Full Astichi suite passes.
- The lifecycle benchmark still reports native counters without
  builder-adapter fallback.

Expected performance movement:

- None required. This is a correctness prerequisite for P2b/P2c.

Tag after success: `perf-native/p2a-package-parity`.

Stop if:

- RustPython AST shape prevents exact parity for a Python surface that Astichi
  already supports. Patch the native AST normalization design before cutting
  over.
- Native would need Python `recognize_markers(...)` on the hot path to pass
  parity.

## Phase P2b: Native Package-Backed Facade Projection

Goal: make the Python facade consume native package-v2 rows as the lower
projection in native-selected mode without triggering adapter fallback.

Work:

- Rebuild `LowerTemplateBinding` rows from the native package-v2 snapshot when
  native is selected.
- Keep explicit debug/source/materialization projection hooks available.
- Preserve compatibility projection records only where candidate objects still
  require Python `InventoryRecord` instances.
- Add counters or focused tests proving native-selected compile no longer uses
  Python package rows as the authoritative lower projection.

Acceptance:

- Native-selected compile returns a facade whose lower package rows are native
  package-v2 rows.
- Existing diagnostics and structural snapshots still have a projection path.
- The lifecycle benchmark reports native counters, no builder-adapter fallback,
  and no large `rebuild_composable` regression.
- Full Astichi suite passes.

Expected performance movement:

- Small or neutral. This removes a prerequisite boundary but still leaves
  Python inventory construction in native compile until P2c.

Tag after success: `perf-native/p2b-facade-projection`.

Stop if:

- Candidate compatibility still requires enough Python `InventoryRecord`
  reconstruction that the checkpoint would be misleading.

## Phase P2c: Native Compile Without Python Lower Extraction

Goal: when native is selected, `astichi.compile(...)` should stop building the
Python lower template and Python inventory merely to attach native metadata.

Work:

- Route native-selected compile source through native parser, pattern
  extraction, package creation, and template registration directly.
- Keep Python-authored validation only where it has not yet been ported, but do
  not build Python lower records for candidate lookup.
- Add native parity coverage for any validation still needed on the hot path.
- Make debug inventory and structural snapshots project from the native package
  only when requested.
- Ensure `select_lower_engine("auto")` remains the single routing decision.

Acceptance:

- Native compile success path does not call Python
  `register_inventory_template(...)`.
- Native compile success path does not call Python `build_inventory(...)` to
  rediscover lower records.
- Any Python `InventoryRecord` objects still needed by compatibility candidate
  APIs are synthesized as projections from native package-v2 rows, not from the
  Python inventory extractor.
- Candidate lookup treats native package/template rows as authoritative; the
  Python projection is an adapter artifact until P3/P4 remove the remaining
  compatibility object boundary.
- P2a native package/snapshot parity remains green.
- Full Astichi suite passes.
- YIDL lifecycle workload still runs.

Expected performance movement:

- Native mode should improve modestly by removing duplicate compile-time lower
  extraction.
- `rebuild_composable`, per-edge candidate lookup, and materialization hot
  counts are not expected to drop in this phase; P3, P4, and P6 own those cuts.

Tag after success: `perf-native/p2c-native-compile`.

Stop if:

- Native extraction lacks a current surface that Python compile accepts.
- Diagnostics require data not present in the native package contract.

## Phase P3a: Materialized Artifact Wrap

Goal: remove Python `_rebuild_composable(...)` from the already-materialized
native/lower artifact path.

Work:

- Replace the post-materialization `_rebuild_composable(...)` call with a cheap
  already-materialized composable wrapper.
- Do not run Python `recognize_markers(...)`, `analyze_names(...)`,
  `build_inventory(...)`, or lower-template registration merely to wrap the
  final artifact.
- Keep unresolved-Astichi-demand validation as a narrow artifact scan instead
  of full re-lowering.
- Preserve final source/executable behavior and explicit debug/source artifact
  copy APIs.

Acceptance:

- Native `context_lcm` counter runs show `rebuild_composable` drop from the
  P2c count of `8` to zero, or present only in explicit fallback/debug paths.
- Existing final goldens pass.
- Full Astichi suite passes.
- YIDL lifecycle workload runs.

Expected performance movement:

- This should remove the currently measured `rebuild_composable` bucket.
- Native mode should improve, but per-edge candidate lookup and apply counts
  remain until P4.

Tag after success: `perf-native/p3a-artifact-wrap`.

Stop if:

- The final artifact wrapper requires public inventory/descriptor semantics
  that cannot be represented without full Python re-lowering.
- The narrow unresolved-demand scan cannot match current final artifact
  validation behavior.

## Phase P3b: Native Source Specialization

Goal: remove Python `_rebuild_composable(...)` from native-selected source
specialization paths.

Work:

- Route `.bind(...)`, `.bind_identifier(...)`, `with_keep_names(...)`, and
  edge-local `apply_source_overlay(...)` through a native-selected
  specialization path.
- Preserve Python ownership of external object values, but keep structural
  metadata changes native-owned after specialization.
- Avoid `ast.unparse(...)` as the normal native specialization path.
- Add counters that distinguish native bind, identifier, and keep-name
  specialization from Python `rebuild_composable`.
- Keep emitted-source and debug projection behavior available through explicit
  artifact copy.

Acceptance:

- Focused tests prove native `.bind(...)`, `.bind_identifier(...)`, and
  keep-name paths do not call Python `_rebuild_composable(...)`.
- Existing identifier binding, external binding, keep-name, managed import, and
  pyimport goldens pass.
- Full Astichi suite passes.
- YIDL lifecycle workload runs.

Expected performance movement:

- This removes rebuild cost for source specialization outside the final artifact
  wrapper.
- Lifecycle movement may be smaller than P3a if the workload's remaining
  rebuilds were mostly final artifact wraps.

Tag after success: `perf-native/p3b-specialization`.

Stop if:

- Source specialization requires Python AST mutation because the native package
  lacks a required operation.
- External-value ownership becomes ambiguous across Python/native lifetime
  boundaries.

## Phase P4: Batched Native Scope Resolution

Goal: stop crossing the Python/native boundary once per candidate lookup and
once per apply operation.

Work:

- Add a native batch API that accepts a sequence of resource requests and
  applies compatible candidate results against one native assembly state.
- The batch request must cover composable resources, external values,
  identifier binds, build path selectors, owner selectors, order, and
  edge-local overlays.
- Keep the existing Python `AssemblyScope.find_candidates(...)` and
  `apply(...)` APIs as compatibility wrappers, but route batch-capable callers
  through the batch API.
- Return compact diagnostics for missing or ambiguous resources without
  projecting full inventory.
- Add counters for batch size, candidate count, and native apply count.

Acceptance:

- Focused native scope tests cover batch composable, external, and identifier
  resolution.
- Existing per-call APIs still pass their tests.
- Full Astichi suite passes.
- YIDL lifecycle workload can use the batch route or an adapter that emits the
  same request sequence.

Expected performance movement:

- `candidate_lookup_lower` and `assembly_scope_apply` should drop materially.
- Native call count should drop from thousands of small calls to a small number
  of batches.

Tag after success: `perf-native/p4-batch-scope`.

Stop if:

- The YIDL assembly order cannot be represented as an explicit request stream.
- Batch diagnostics lose enough context that failures become hard to debug.

## Phase P5: YIDL Assembly Integration

Goal: put the batch scope API on the real lifecycle-generation hot path.

Work:

- Update Astichi/YIDL-facing assembly adapters to emit the batch request stream
  where possible.
- Keep compatibility wrappers for non-batch callers.
- Validate the generated lifecycle output with existing final goldens and the
  `context_lcm` benchmark.
- Add a focused integration test or fixture proving the lifecycle path uses the
  batch counters.

Acceptance:

- YIDL lifecycle workload uses native batch counters in native mode.
- Per-operation `candidate_lookup_lower` and `assembly_scope_apply` no longer
  dominate the counter report.
- Full Astichi suite passes.
- Available YIDL/Pyrolyze validation passes.

Expected performance movement:

- Native `context_lcm` should be in the "good" range, around 1.2s, unless final
  artifact creation has become the dominant cost.

Tag after success: `perf-native/p5-yidl-batch`.

Stop if:

- YIDL needs an API break beyond the scope API boundary already accepted for
  this refactor.
- The integration requires restoring full Python inventory projection on the
  success path.

## Phase P6: Native Materialization And Artifact Boundary

Goal: keep materialization, hygiene, and final AST construction in the lower
layer until the explicit artifact boundary.

Work:

- Materialize from native occurrence/edge/overlay state into a native
  workspace.
- Run hygiene and managed import placement from native package/state data.
- Copy CPython AST nodes only at `copy_python_ast`, public runtime compile, or
  explicit debug/source rendering boundaries.
- Keep structural and final-source goldens as the correctness gates.
- Add counters for native materialization, native hygiene, and CPython AST copy.

Acceptance:

- Native materialization does not call Python builder merge or Python
  materializer on supported current surfaces.
- Existing final goldens pass.
- Structural materialization snapshots remain deterministic.
- Full Astichi suite passes.
- YIDL lifecycle workload runs and reports native materialization counters.

Expected performance movement:

- Native `to_executable_ast` and lower materialization buckets should shrink or
  move to native counters.
- Strong target range, about 0.8-1.0s, becomes plausible after this phase.

Tag after success: `perf-native/p6-materialization`.

Stop if:

- Native materialization needs lower-template data that is not part of the v2
  package contract.
- Current Python goldens rely on incidental Python AST mutation order rather
  than documented output behavior.

## Phase P7: Cleanup, Slow-Path Projection, And Closeout

Goal: remove temporary hybrid adapters from the native success path and make the
performance result easy to verify.

Work:

- Delete or quarantine temporary Python-native mirror paths that are no longer
  used by native success execution.
- Make `scope.inventory`, inventory printing, structural debug projection, and
  source rendering explicit slow paths.
- Keep Python reference behavior available and tested.
- Update docs to describe the production native boundary and the remaining
  slow-path projections.
- Record final local benchmark summary without committing raw machine logs.

Acceptance:

- Native default remains capability-gated.
- Forced Python remains available.
- Full Astichi suite passes.
- Available Python-version matrix passes when practical.
- YIDL lifecycle workload meets at least the "good" target or the remaining
  non-Astichi bottleneck is measured and documented.

Expected performance movement:

- This phase should stabilize the result, not deliver the main speedup.

Tag after success: `perf-native/p7-closeout`.

Stop if:

- Cleanup would remove a public compatibility behavior before a replacement API
  is documented.
- Final performance is still slower than forced Python and the remaining cause
  is not identified.

## Counter Exit Criteria

The roll-build should not close while native mode still looks like the current
hybrid profile.

Closeout counter shape should be:

- `native_*` counters present and dominant for lower operations;
- Python `rebuild_composable` absent or only present in explicit debug/fallback
  paths;
- Python `candidate_lookup_lower` and `assembly_scope_apply` no longer called
  once per YIDL edge/resource;
- Python `to_executable_ast` replaced by native materialization plus explicit
  CPython AST copy counters;
- debug inventory projection absent from success-path counter runs.

## Non-Goals For This Roll-Build

- Do not add a cache as the first answer to cold-start performance.
- Do not use private CPython compiler internals as the primary artifact
  boundary.
- Do not remove the Python reference lower engine.
- Do not hard-code YIDL-specific surfaces into the generic native engine.
- Do not make timing assertions part of normal unit tests.
