# Native Performance Roll-Build Plan

Status: revised after `perf-native/p6a-artifact-boundary`.

This plan starts after the native lower-engine path is functionally selectable
by default. At this point native correctness is proven for the current Astichi
suite, but the performance result is still negative because the default native
path is hybrid: Python builds and rebuilds much of the lower metadata, then the
native engine mirrors part of the same state and answers some scope queries.

The goal of this plan is to remove Python success-path work, not to add more
native mirrors around it.

## Current Baseline

The original local profile for `pyrolyze.runtime.context_lcm` was:

| Mode | Wall time | Meaning |
| --- | ---: | --- |
| `ASTICHI_LOWER_ENGINE=python` | about 1.9-2.0s | Python lower path only |
| default `auto` selecting native | about 2.4s | native hooks active, but hybrid |

The latest post-`p6a` local counter run changes the shape materially:

| Mode | Wall time | Meaning |
| --- | ---: | --- |
| `ASTICHI_LOWER_ENGINE=python` | about 0.83s | Python lower path through the new batch facade |
| `ASTICHI_LOWER_ENGINE=native` | about 0.94s | native-selected path, still slower due to native batch/query overhead |

The old Python hot counters are no longer the measured problem:

- `rebuild_composable=0`
- `candidate_lookup_lower=0`
- `assembly_scope_apply=0`
- `to_executable_ast=0`
- `copy_python_ast=8`

The remaining measured native gap is scope execution shape:

- `native_scope_batch=1057`
- `native_scope_batch_size=1659`
- `native_candidate_query_composable=591`
- `native_candidate_query_external=421`
- `native_candidate_query_identifier=647`
- `native_scope_append_edge=591`
- `native_scope_append_overlay=1068`
- `native_scope_mark_satisfied=1068`

These counters show that P4/P5 moved the public API and YIDL runtime onto a
request-stream facade, but did not yet make the native engine execute the
whole stream authoritatively in one native operation. The Python facade still
loops over requests and still mirrors enough state for Python materialization.

Native counters prove the native path is active:

- `native_candidate_query_composable`
- `native_candidate_query_external`
- `native_candidate_query_identifier`
- `native_scope_append_edge`
- `native_scope_append_occurrence`
- `native_scope_append_overlay`
- `native_scope_mark_satisfied`

The remaining native counters now explain the regression:

- native candidate query counts scaling with request count;
- native append/mark counts scaling with request count;
- facade batch calls that cannot chain target application with immediately
  dependent binding requests;
- Python lower-state mirror replay kept alive for materialization compatibility.

Performance work is not complete until native mode executes request batches in
the lower layer without re-entering Python per request, then materializes from
that native-owned state without requiring Python lower-state replay.

## Performance Target

Use these targets for planning. Do not encode them as brittle unit-test timing
thresholds.

| Result | `context_lcm` target | Notes |
| --- | ---: | --- |
| acceptable | <= forced Python | native no longer regresses |
| good | <= 0.8s | true native batch apply beats the forced Python batch facade |
| strong | 0.6-0.75s | native scope and materialization own the hot path |
| stretch | 0.5-0.7s | requires YIDL/import/startup/final artifact costs to also be tight |

## Current Roll-Build State

Completed checkpoints:

- `perf-native/p0-baseline`
- `perf-native/p1-facade`
- `perf-native/p2a-package-parity`
- `perf-native/p2b-facade-projection`
- `perf-native/p2c-native-compile`
- `perf-native/p3a-artifact-wrap`
- `perf-native/p3b-shadow-fix`
- `perf-native/p3b-specialization`
- `perf-native/p4-batch-scope`
- `perf-native/p5-yidl-batch`
- `perf-native/p6a-artifact-boundary`

Remaining checkpoints:

- P5b: true native batch scope engine.
- P5c: chained YIDL request coalescing.
- P6b: native operation materialization.
- P6c: native hygiene and artifact cutover, tagged as
  `perf-native/p6-materialization`.
- P7: cleanup and closeout.

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

## Phase P4: Batched Scope Facade

Goal: establish an ordered request-stream API that can later be executed by
the native lower engine as one operation.

Status: completed as `perf-native/p4-batch-scope`.

Completed work:

- `perf-native/p4-batch-scope` completed the public request-stream facade and
  `AssemblyScope.apply_batch(...)`.
- Added compatibility wrappers so existing `find_candidates(...)` and
  `apply(...)` callers continue to work.
- Proved the YIDL assembly order can be represented as an explicit request
  stream.
- Added facade-level counters for batch count, request count, and candidate
  count.

Result:

- Public Python counters `candidate_lookup_lower` and `assembly_scope_apply`
  can be removed from the hot report when callers use `apply_batch(...)`.
- This checkpoint intentionally did not complete true native batch execution.
  The facade still resolves and applies one request at a time internally.
- P5b owns the native engine implementation that will make this API a real
  lower-layer batch operation.

## Phase P5: YIDL Batch Facade Integration

Goal: put the ordered request-stream facade on the real lifecycle-generation
hot path.

Status: completed as `perf-native/p5-yidl-batch`.

Completed work:

- `perf-native/p5-yidl-batch` completed YIDL runtime integration and removed
  the public per-call `candidate_lookup_lower` / `assembly_scope_apply`
  counters from the lifecycle workload.
- Updated the YIDL-facing assembly runtime to emit `BindingRequest` streams.
- Preserved compatibility wrappers for non-batch callers.
- Validated the generated lifecycle output through the existing suites.

Result:

- The lifecycle workload now emits 1057 batch facade calls for 1659 ordered
  requests.
- Native query/apply counters still scale with those requests because P5 used
  the facade loop instead of a native batch engine.
- P5c owns coalescing target insertion plus immediately dependent bindings so
  the request count can stay explicit while the batch-call count drops.

## Phase P5b: True Native Batch Scope Engine

Goal: make `AssemblyScope.apply_batch(...)` delegate an ordered request stream
to one native operation instead of looping through native candidate/apply calls
from Python.

Work:

- Add a native `assembly_state_apply_request_batch(...)` API that accepts an
  ordered request stream against one native assembly state.
- The native request stream must cover:
  - composable resources by native template handle plus build name/index/order;
  - external values by Python-owned request token;
  - identifier values by spelling;
  - demand name, build selector, owner selector;
  - equivalent-demand-site selection for binding marker coalescing.
- Native execution must resolve one request, apply it, update native indexes,
  then continue to the next request so later selectors can observe earlier
  identifier/external overlays and inserted occurrences.
- Return a compact event stream for Python compatibility state:
  selected target record, created occurrence build path, appended edge,
  appended overlay, satisfied record, and diagnostics for missing/ambiguous
  requests.
- Keep Python ownership of external object values, but store them by returned
  native overlay id without re-querying inventory.
- Add explicit counters for:
  `native_scope_batch_engine`,
  `native_scope_batch_engine_request_count`,
  `native_scope_batch_engine_candidate_count`,
  and temporary `python_scope_mirror_replay` if Python lower-state replay is
  still needed for materialization compatibility.
- Keep the old facade loop as fallback when native is unavailable or a request
  surface is not yet supported.

Acceptance:

- Focused native tests prove a mixed batch can insert a composable, bind
  identifiers, bind externals, and then resolve later requests against the
  modified native state.
- Missing and ambiguous diagnostics identify the failing request index/name
  without projecting full inventory.
- Existing `find_candidates(...)` and `apply(...)` compatibility APIs still
  pass their tests.
- Full Astichi suite passes.
- Full available YIDL suite passes.
- Lifecycle benchmark shows `native_scope_batch_engine` counters and no longer
  reports per-request `native_candidate_query_*` and `native_scope_append_*`
  counters as the dominant shape.

Expected performance movement:

- Native should become competitive with forced Python, or the remaining gap
  should move to explicitly named Python mirror replay/materialization counters.

Tag after success: `perf-native/p5b-native-batch-engine`.

Stop if:

- Native cannot update request-order-dependent indexes without data missing
  from the package-v2 contract.
- Python lower-state replay remains as expensive as the current facade loop and
  cannot be isolated behind a temporary compatibility counter.

## Phase P5c: Chained YIDL Request Coalescing

Goal: reduce batch call count by allowing one YIDL contribution to emit a
target request followed by binding requests that refer to the target result.

Work:

- Extend the batch request contract with a stable "previous result" reference
  that can bind against the just-created occurrence/build path.
- Update YIDL contribution application so target insertion and contribution
  bindings can be emitted as one ordered request stream when the build path is
  concrete.
- Preserve the existing separate request behavior for dynamic selectors and
  cases where later requests cannot safely refer to a prior result.
- Add focused YIDL runtime tests for target-plus-binding coalescing and for a
  dynamic-selector fallback.
- Add counters for coalesced contributions and fallback contributions.

Acceptance:

- Full Astichi suite passes.
- Full available YIDL suite passes.
- Lifecycle benchmark reduces `native_scope_batch` / native batch-engine call
  count materially below the P5b count while preserving the same request count.
- Final generated lifecycle output is unchanged.

Expected performance movement:

- Native batch overhead should drop again, especially on workloads where most
  contributions have one target request followed by one or more bindings.

Tag after success: `perf-native/p5c-yidl-chain-batches`.

Stop if:

- Chained requests blur YIDL semantics or make failure diagnostics ambiguous.
- Dynamic selectors cannot be cleanly separated from concrete-selector
  coalescing.

## Phase P6: Native Materialization And Artifact Boundary

Goal: keep materialization, hygiene, and final AST construction in the lower
layer until the explicit artifact boundary.

Status note:

- `perf-native/p6a-artifact-boundary` is the safe artifact-boundary
  sub-checkpoint: already-materialized lower artifacts copy directly to
  CPython AST through an explicit `copy_python_ast` counter, so the lifecycle
  workload no longer reports `to_executable_ast` on that path.
- The full `perf-native/p6-materialization` checkpoint remains open until the
  native workspace can recursively materialize the current supported operation
  stream and run the corresponding hygiene/managed-import decisions without
  relying on the Python lower materializer.

Remaining work:

- P6b: recursively materialize native operation streams into a native
  workspace.
- P6c: move hygiene, managed imports, and final artifact cutover to the native
  lower layer.

Do not tag `perf-native/p6-materialization` until both subphases are complete.

### Phase P6b: Native Operation Materialization

Goal: materialize the native occurrence/edge/overlay graph recursively into a
native workspace for the current operation stream.

Work:

- Add a native orchestration API that starts from the root occurrence, sorts
  edge operations deterministically by order and edge id, materializes child
  occurrences, and applies operations into the parent workspace.
- Reuse existing native workspace primitives for expression, block,
  parameter, call-argument, identifier overlay, external overlay, and literal
  `astichi_ref(...)` lowering.
- Add missing native workspace primitives for current operation surfaces not
  covered by the primitive API, especially elif clause insertion and
  defaulted/fallback block-hole handling.
- Pass Python-owned external values to native as validated literal expression
  source or a compact literal payload map keyed by overlay id.
- Return a native materialized artifact handle plus a deterministic structural
  materialization snapshot.
- Keep Python lower materialization available as fallback and oracle.
- Add counters for `native_materialize_operation_stream`,
  `native_materialize_workspace_copy`, and explicit fallback.

Acceptance:

- Native materialization snapshots match Python lower materialization snapshots
  for expression, block, params, call-args, named-variadic call-args, elif,
  identifier overlays, external overlays, literal refs, and defaulted block
  holes.
- Existing final goldens pass when native operation materialization is enabled
  for supported surfaces.
- Full Astichi suite passes.
- Full available YIDL suite passes.
- Lifecycle benchmark reports native materialization counters and no Python
  builder merge on the success path.

Expected performance movement:

- Lower materialization plan/build buckets should shrink or move to native
  counters. If Python mirror replay remains, this phase may be neutral until
  P6c.

Tag after success: `perf-native/p6b-native-operation-materialization`.

Stop if:

- Operation ordering cannot be reproduced from native state without adding
  data to the request/event contract.
- A current operation surface has no native AST manipulation strategy that can
  preserve final golden output.

### Phase P6c: Native Hygiene And Artifact Cutover

Goal: complete the lower-layer responsibility boundary: hygiene, managed
imports, unresolved gates, and final artifact copy run from native package/state
data until the explicit CPython AST boundary.

Work:

- Execute native hygiene operations represented by the package-v2/materialized
  state contract:
  `rename_if_collides`, `keep_name`, `managed_import_request`,
  `gate_no_unresolved`, marker stripping, and managed-import insertion.
- Preserve Python reference behavior as oracle, but do not call Python hygiene
  or Python materialization on native success paths.
- Make `scope.build()` return the native materialized artifact wrapper for
  native-selected supported states.
- Copy CPython AST nodes only at `copy_python_ast`, public runtime compile, or
  explicit debug/source rendering boundaries.
- Keep source rendering and inventory projection as explicit slow/debug paths.
- Add counters for `native_hygiene`, `native_managed_imports`,
  `native_unresolved_gate`, `copy_python_ast`, and fallback.

Acceptance:

- Native materialization does not call Python builder merge or Python
  materializer on supported current surfaces.
- Existing final goldens pass.
- Structural materialization snapshots remain deterministic.
- Full Astichi suite passes.
- Full available YIDL suite passes.
- YIDL lifecycle workload runs and reports native materialization/hygiene
  counters.
- Lifecycle counter shape has `copy_python_ast` only at the explicit artifact
  boundary and no Python lower materialization success-path counters.

Expected performance movement:

- Strong target range, about 0.6-0.75s, becomes plausible after this phase if
  P5b/P5c also removed the native batch overhead.

Tag after success: `perf-native/p6-materialization`.

Stop if:

- Native materialization needs lower-template data that is not part of the v2
  package contract.
- Current Python goldens rely on incidental Python AST mutation order rather
  than documented output behavior.

## Phase P7: Cleanup, Slow-Path Projection, And Closeout

Goal: remove temporary hybrid adapters from the native success path and make the
performance result easy to verify.

Prerequisite:

- P5b, P5c, and full P6 must be complete. Do not start cleanup while Python
  lower-state mirror replay or Python materialization fallback remains part of
  the native success path.

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
- native candidate query/apply/append counters no longer scaling one-for-one
  with YIDL resource requests; batch-engine counters should describe the
  request stream directly;
- Python `to_executable_ast` replaced by native materialization plus explicit
  CPython AST copy counters;
- Python lower-state mirror replay absent from native success-path counter
  runs, or explicitly measured as a remaining blocker before closeout;
- debug inventory projection absent from success-path counter runs.

## Non-Goals For This Roll-Build

- Do not add a cache as the first answer to cold-start performance.
- Do not use private CPython compiler internals as the primary artifact
  boundary.
- Do not remove the Python reference lower engine.
- Do not hard-code YIDL-specific surfaces into the generic native engine.
- Do not make timing assertions part of normal unit tests.
