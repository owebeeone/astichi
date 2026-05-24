# Remaining Roll-Build Plan

Status: ready-to-run completion plan.

This document breaks the remaining lower-engine refactor into roll-build
checkpoints starting after `perf-refactor/slice-10b`. It is the operational
plan for finishing the Python reference implementation through Slice 13 and
then, if the profile still justifies it, implementing the native library
components behind the same lower-engine contract.

## Roll-Build Rules For This Plan

- Start from a clean Astichi tree at or after `perf-refactor/slice-10b`.
- If a new rollout starts later, create one start tag before changes, for
  example `perf-refactor/completion-start`.
- Commit and tag every checkpoint only after focused verification and the full
  Astichi suite pass.
- Keep success-path behavior in structural or final goldens. Use bespoke tests
  only for narrow diagnostics, invalid inputs, counters, or adapter mechanics.
- Do not move to native implementation during the Python completion roll-build.
  Finish the Python reference path first, then start the native library
  roll-build from the Slice 13c profile gate.
- Stop when a checkpoint would be misleadingly partial, when materialization
  needs a new operation concept, or when YIDL cannot be validated after a
  caller migration.

## Current Baseline

Completed tags:

- `perf-refactor/slice-7a`: lower-index lookup exists as
  `AssemblyScope.find_candidates(...)`.
- `perf-refactor/slice-7b`: YIDL and Astichi success-path candidate lookup use
  `AssemblyScope.find_candidates(...)`; standalone inventory lookup is
  compatibility/debug only and private.
- `perf-refactor/slice-7.5a`: transient differential harness compares lower
  lookup with the projected-inventory adapter and stores final builder-adapter
  outputs in structural goldens.
- `perf-refactor/slice-11a`: lower materialization-plan construction emits
  operation and hygiene streams for the first edge/overlay subset without
  changing final output.
- `perf-refactor/slice-11b`: explicit lower materialization supports
  expression insertion with external/identifier overlays; unsupported surfaces
  use a counted adapter fallback.
- `perf-refactor/slice-11c`: explicit lower materialization supports ordinary
  block insertion with edge ordering.
- `perf-refactor/slice-11d`: `scope.build(...)` automatically selects lower
  materialization for closed Slice 11 states and counts adapter fallback for
  unsupported states.
- `perf-refactor/slice-12a1`: parameter-hole materialization is represented in
  lower operation/hygiene streams and differential fixtures, without final
  lower parameter output yet.
- `perf-refactor/slice-12a2`: simple parameter-hole payloads materialize on the
  lower path; unsupported call-argument payloads still exercise the counted
  adapter fallback.
- `perf-refactor/slice-12a3`: simple elif payloads materialize on the lower
  path with ordered right-folding; boundary/hygiene elif payloads still
  exercise the counted adapter fallback.
- `perf-refactor/slice-12b1`: unfilled defaulted block holes materialize their
  fallback suites on the lower path, with fallback selection visible in lower
  structural snapshots.
- `perf-refactor/slice-12b2`: static managed pyimports materialize on the lower
  path with managed-import requests visible in lower hygiene snapshots;
  collision and dynamic-module cases still exercise the counted adapter
  fallback.
- `perf-refactor/slice-12c1`: simple boundary import/pass/export markers in
  block payloads materialize on the lower path, with marker-strip decisions
  visible in lower hygiene snapshots.
- `perf-refactor/slice-12c2`: simple keep-name/collision hygiene materializes
  on the lower path, with keep and rename decisions visible in lower hygiene
  snapshots.
- `perf-refactor/slice-12c3a`: simple variadic call-argument holes materialize
  on the lower path, with `splice_call_arguments` visible in lower operation
  snapshots.
- `perf-refactor/slice-12c3b`: simple boundary imports in elif payloads
  materialize on the lower path, with marker-strip decisions visible in lower
  hygiene snapshots.
- `perf-refactor/slice-12c3c`: static pyimport name collisions materialize on
  the lower path, with managed-import and rename decisions visible in lower
  hygiene snapshots.
- `perf-refactor/slice-12c3`: full lower materialization gate for the current
  migrated surface suite.
- `perf-refactor/slice-13a`: composable scope applies update lower state and
  defer legacy builder graph mutations until an adapter fallback is requested.
- `perf-refactor/slice-13b`: standalone inventory candidate lookup is removed
  from the public assembler facade and retained only as the private
  `find_candidates_in_inventory(...)` debug helper.
- `perf-refactor/slice-13c`: the Python lower refactor closes with the YIDL
  lifecycle import workload using lower materialization for all 8 decorated
  classes and with YIDL edge/no-op counters reported separately from Astichi
  lower counters.
- `perf-refactor/slice-8`: `scope.inventory` reads through lower debug
  projection.
- `perf-refactor/slice-9a`: legacy occurrence-inventory replacement is gone
  from scope add/apply.
- `perf-refactor/slice-10a`: external applies are lower overlays.
- `perf-refactor/slice-10b`: identifier applies are lower overlays with a
  resolved-name lookup/projection view.

The remaining work is primarily:

- finishing temporary compatibility/debug adapters once materialization no
  longer needs them;
- making `scope.build(...)` materialize from lower state;
- expanding lower materialization and hygiene surface coverage;
- deleting temporary adapters.

## Checkpoint 7b: Move Callers To Scope Lookup

Goal: remove success-path dependence on `find_candidates(scope.inventory, ...)`
for Astichi/YIDL assembly.

Work:

- Update YIDL assembly runtime callers to call
  `scope.find_candidates(resource, ...)` directly.
- Update Astichi success-path tests and performance-counter tests that currently
  use `find_candidates(scope.inventory, ...)`.
- Keep projected-inventory lookup as a debug and compatibility adapter only;
  Slice 13b later privatizes it as `find_candidates_in_inventory(...)`.
- Add a focused counter test proving candidate lookup on the updated hot path
  does not call `debug_inventory_projection`.
- Keep missing/ambiguous diagnostics equivalent for the caller-migrated path.

Acceptance:

- YIDL assembly runtime no longer projects `scope.inventory` for candidate
  lookup.
- Astichi focused assembler tests pass.
- Full Astichi suite passes.
- Available YIDL generation/runtime goldens pass, or the checkpoint stops with
  the exact YIDL verification gap documented.
- Counters show direct lower lookup on the migrated hot path.

Stop if:

- YIDL relies on raw `InventoryRecord` behavior that cannot be represented by
  candidate adapter objects without widening the lower candidate handle.
- Missing/ambiguous diagnostics lose target/resource information.

Tag: `perf-refactor/slice-7b`.

## Checkpoint 7.5a: Differential Harness Skeleton

Goal: add an opt-in transient harness before replacing materialization.

Work:

- Add a constrained differential harness for named fixtures, not broad random
  fuzzing yet.
- Cover block insertion, expression insertion, external overlay, identifier
  overlay, and single-add satisfaction.
- Compare lower debug inventory against the legacy-compatible projection where
  both are intentionally available.
- Compare final source for cases still materialized through the builder adapter.
- Store any mismatch as a reduced structural or final golden before fixing it.

Acceptance:

- Harness can run as a focused command or focused pytest file.
- Harness is marked transient in code and docs.
- Failures name the fixture and the compared artifacts.
- Full Astichi suite passes.

Stop if:

- The harness requires duplicating broad success-path assertions already owned
  by goldens.
- Lower state cannot represent one of the simple supported surfaces without a
  design patch.

Tag: `perf-refactor/slice-7.5a`.

## Checkpoint 11a: Materialization Plan Builder

Goal: produce lower-owned materialization and hygiene streams without changing
final output yet.

Work:

- Build a materialization-plan constructor from lower occurrences, edges,
  overlays, record state, and root selection.
- Emit operation stream entries for expression insert, block insert, external
  bind, and identifier bind.
- Emit a minimal hygiene stream even when the first subset does not need rename
  decisions.
- Snapshot plans through structural goldens.
- Count materialization-plan construction separately from final artifact
  materialization.

Acceptance:

- Structural materialization snapshots round-trip.
- Operation stream uses registered operation keys.
- Hygiene stream exists and is deterministic.
- No final-output behavior changes.
- Full Astichi suite passes.

Stop if:

- Plan entries cannot locate target/source records without reconstructing
  intent from Python `Inventory`.
- External or identifier overlays cannot be expressed as lower-owned stream
  entries.

Tag: `perf-refactor/slice-11a`.

## Checkpoint 11b: Expression And Overlay Materialization

Goal: materialize the smallest useful subset from lower state.

Work:

- Implement lower-owned final artifact construction for expression insertion.
- Apply external and identifier overlays during lower materialization for the
  same subset.
- Keep builder adapter fallback only for unsupported surfaces, with explicit
  counters.
- Add final-output goldens or reuse existing goldens for the supported subset.
- Extend the differential harness for this subset.

Acceptance:

- Supported expression/external/identifier fixtures no longer use builder graph
  materialization.
- Final source/AST output matches existing behavior.
- Adapter fallback count is zero for the supported fixtures and visible for
  unsupported ones.
- Full Astichi suite passes.

Stop if:

- CPython AST artifact copy requires metadata not present in the lower locator
  or template records.
- Overlay application needs eager AST rewrites for selector correctness.

Tag: `perf-refactor/slice-11b`.

## Checkpoint 11c: Block Materialization

Goal: route ordinary block insertion through lower materialization.

Work:

- Implement block insert flattening from lower edges.
- Preserve insertion order.
- Preserve single-add satisfaction behavior.
- Add materialization-plan and final-output goldens for single and multi-add
  block insertion.
- Extend differential harness block cases.

Acceptance:

- Block insertion fixtures materialize from lower state.
- Counters show no builder adapter materialization for supported block cases.
- Diagnostics for unresolved block holes remain useful.
- Full Astichi suite passes.

Stop if:

- Block insertion needs source-scope or hygiene information missing from lower
  records.
- Multi-add order cannot be represented by current edge ordering.

Tag: `perf-refactor/slice-11c`.

## Checkpoint 11d: Lower Build Selection For Supported Subset

Goal: make `scope.build(...)` select lower materialization for every Slice 11
supported surface.

Work:

- Add a capability check for lower-materializable scope state.
- Use lower materialization automatically when all live state is in the Slice
  11 subset.
- Keep unsupported state on the counted builder adapter path.
- Add focused counters around lower materialization, final artifact copy, and
  adapter fallback.
- Update active docs with the exact supported subset.

Acceptance:

- Supported subset uses lower materialization by default.
- Unsupported cases continue to pass through the adapter and are counted.
- Full Astichi suite passes.

Stop if:

- Capability checks become a second pattern system instead of using registered
  surface/operation metadata.

Tag: `perf-refactor/slice-11d`.

## Checkpoint 12a1: Parameter Operation Stream

Goal: represent parameter-hole materialization in lower streams.

Work:

- Add parameter-hole plan entries.
- Snapshot target parameter records, payload records, operation stream entries,
  and hygiene stream placeholders.
- Extend differential harness with a parameter fixture.

Acceptance:

- Structural plan golden covers parameter insertion.
- No final-output behavior changes yet.
- Full Astichi suite passes.

Stop if:

- Parameter payload ordering or duplicate-name validation cannot be represented
  without rescanning Python AST inventory.

Tag: `perf-refactor/slice-12a1`.

## Checkpoint 12a2: Parameter Final Materialization

Goal: materialize parameter holes from lower state.

Work:

- Splice parameter payloads through lower materialization.
- Preserve duplicate final parameter diagnostics.
- Add or update final-output goldens for parameter insertion.
- Route supported parameter fixtures away from the builder adapter.

Acceptance:

- Parameter final-output goldens pass.
- Duplicate-parameter diagnostics remain covered by focused tests.
- Full Astichi suite passes.

Stop if:

- Signature rewriting needs hygiene decisions not yet represented in the lower
  hygiene stream.

Tag: `perf-refactor/slice-12a2`.

## Checkpoint 12a3: Elif Materialization

Goal: move elif target/payload materialization to lower operation streams and
final output.

Work:

- Add elif clause plan entries and final right-folding behavior.
- Preserve order and unresolved-target diagnostics.
- Add structural and final-output goldens for multiple branches.
- Extend differential harness with elif cases.

Acceptance:

- Elif final-output goldens pass.
- Lower materialization does not reconstruct elif intent from Python
  `Inventory`.
- Full Astichi suite passes.

Stop if:

- Clause insertion exposes a missing generic clause operation needed by future
  match/case or exception-handler surfaces.

Tag: `perf-refactor/slice-12a3`.

## Checkpoint 12b1: Defaulted Block Holes

Goal: move default/fallback block-hole decisions to lower materialization.

Work:

- Represent filled-vs-fallback selection in materialization and hygiene
  snapshots.
- Materialize fallback suites when no insert satisfies the target.
- Reject managed imports inside fallback suites through the existing diagnostic
  path.
- Add structural and final-output goldens.

Acceptance:

- Filled and fallback defaulted-hole cases pass.
- Default selection is visible in structural snapshots.
- Full Astichi suite passes.

Stop if:

- Fallback branch inactivity cannot be represented in lower state without
  copying discarded AST into the hot path.

Tag: `perf-refactor/slice-12b1`.

## Checkpoint 12b2: Managed Pyimports

Goal: move managed import placement and validation into lower-owned
materialization/hygiene streams.

Work:

- Emit managed-import hygiene operations from lower state.
- Preserve import ordering, aliases, and collision behavior.
- Add structural snapshots for import placement decisions.
- Add or update final-output goldens for pyimport fixtures.

Acceptance:

- Pyimport final-output goldens pass.
- Import placement decisions are visible in hygiene snapshots.
- Full Astichi suite passes.

Stop if:

- Pyimport collision handling requires the broader boundary/hygiene slice first.

Tag: `perf-refactor/slice-12b2`.

## Checkpoint 12c1: Boundary Pass/Import/Export

Goal: lower boundary pass/import/export behavior.

Work:

- Represent boundary imports, passes, and exports as lower hygiene operations.
- Preserve same-scope conflict diagnostics.
- Add structural snapshots for boundary flow.
- Add or update final-output goldens.

Acceptance:

- Boundary final-output goldens pass.
- Scope isolation remains strict.
- Full Astichi suite passes.

Stop if:

- Boundary resolution needs a symbol-table concept missing from lower state.

Tag: `perf-refactor/slice-12c1`.

## Checkpoint 12c2: Keep Names And Collision Rename

Goal: make lower hygiene own keep-name and collision decisions.

Work:

- Emit keep-name and rename-if-collides hygiene operations.
- Preserve lexical keep semantics.
- Preserve unrepairable collision diagnostics.
- Add structural hygiene goldens for keep and collision cases.

Acceptance:

- Hygiene final-output goldens pass.
- Structural snapshots expose keep and rename decisions.
- Full Astichi suite passes.

Stop if:

- Lower hygiene decisions cannot be made without re-entering facade-driven
  materialization.

Tag: `perf-refactor/slice-12c2`.

## Checkpoint 12c3: Full Lower Materialization Gate

Goal: make lower materialization cover all current Astichi final-output
surfaces.

Work:

- Route all current final-output fixtures through lower materialization.
- Keep a counted fallback only for explicitly unsupported debug paths.
- Run the differential harness across every migrated surface family.
- Update active docs with the new materialization ownership statement.

Acceptance:

- All Astichi final-output goldens pass.
- Differential harness covers the migrated surface set.
- Materialization and hygiene are lower-layer responsibilities in code, not
  only design.
- Full Astichi suite passes.

Stop if:

- Any current surface still requires facade reconstruction from Python
  `Inventory`.

Tag: `perf-refactor/slice-12c3`.

## Checkpoint 13a: Remove Hot-Path Builder Adapter

Goal: delete builder graph mutations from scope apply for migrated surfaces.

Work:

- Remove temporary builder add/target mutations from `AssemblyScope.apply`.
- Keep public builder APIs only where they are still supported outside the
  lower scope path.
- Preserve diagnostics through lower candidate/resource formatting.
- Update performance counters to fail if adapter mutation appears in the YIDL
  hot path.

Acceptance:

- YIDL lifecycle-shaped import does not use builder adapter mutation.
- Astichi and available YIDL success goldens pass.
- Full Astichi suite passes.

Stop if:

- A public builder API still needs the old graph mutation semantics and has no
  lower equivalent.

Tag: `perf-refactor/slice-13a`.

## Checkpoint 13b: API Cleanup

Goal: remove temporary compatibility surfaces left from migration.

Work:

- Make standalone inventory candidate lookup clearly debug/compat only or
  remove it if no supported caller remains.
- Remove obsolete tests that only preserve old intermediate representation.
- Replace success-path bespoke tests with structural or final goldens where
  appropriate.
- Update `dev-docs/perf-refactor/AssemblyApiLedger.md`.

Acceptance:

- Supported assembly API is smaller than the starting surface.
- Removed APIs have no Astichi or YIDL callers.
- Full Astichi suite passes.

Stop if:

- A removed surface is still needed by YIDL generated output.

Tag: `perf-refactor/slice-13b`.

## Checkpoint 13c: Counter And Profile Gate

Goal: close the Python refactor with a profile-ready baseline.

Work:

- Retire counters for deleted legacy paths.
- Keep counters for lower candidate lookup, overlays, materialization plan,
  final materialization, debug projection, adapter fallback, and artifact copy.
- Run the import workload introduced in Slice 1.
- Record current performance in the active perf docs.

Acceptance:

- No adapter cost appears in the YIDL import profile.
- The remaining profile clearly separates YIDL no-op edge evaluation from
  Astichi lower-engine work.
- Full Astichi suite passes.

Profile result:

- `docs/validation/perf/yidl_lifecycle_import_baseline.py` reports zero
  `build_merge`, zero `builder_adapter_mutation`, and zero
  `lower_materialization_adapter_fallback` for the
  `pyrolyze.runtime.context_lcm` 8-class lifecycle import workload.
- The same run reports YIDL edge traversal separately under
  `yidl_runtime_counters`: 904 edge calls, 628 contribution selections, 68
  no-match selections, 560 contribution applications, and zero
  empty-resource no-ops.
- Representative wall time is about 0.8 seconds, with about 0.67 seconds in
  YIDL assembly, 0.04 seconds in final AST export/materialization, and about
  0.08 seconds combined in Astichi lower candidate lookup plus scope apply.

Stop if:

- The profile shows material time in a compatibility path that should have been
  deleted in Slice 13a or 13b.

Tag: `perf-refactor/slice-13c`.

## Native Library Roll-Build

Native implementation is included in this completion plan, but it is a separate
roll-build after `perf-refactor/slice-13c`. The Python lower engine remains the
reference implementation and parity oracle.

Do not begin native implementation until:

- the Python lower engine covers the YIDL hot path;
- the Slice 13c profile still misses the performance target;
- remaining time is in Astichi lower-engine work, not YIDL edge evaluation,
  import side effects, test overhead, or unrelated code;
- structural and final goldens are stable enough for Python/native parity.

Stop immediately if the Python lower engine meets the import-time target.

## Native Library Component Map

The native library must implement the same lower-engine contract. It should not
add one native API per Astichi surface. Surface behavior enters through the
registered surface bundle, pattern descriptors, operation descriptors, and
compatibility descriptors.

Native components:

- `native_engine`: owns engine lifetime, handle validation, state allocation,
  error conversion, and Python extension object lifetimes.
- `surface_registry`: consumes the canonical surface bundle, assigns dynamic
  native ids, stores stable-key mappings for snapshots, and rejects unsupported
  operation primitives before work starts.
- `template_store`: stores registered template metadata, source locators,
  source summaries, projection/debug metadata, operation captures, and optional
  native AST/IR references.
- `native_parser_ir`: parses source into a native parser tree or normalized
  Astichi IR when the Slice 14 gate accepts that path; it does not call CPython
  internal compiler APIs.
- `occurrence_store`: stores occurrences, parent links, build paths, live/dead
  state, and per-occurrence overlay handles.
- `record_indexes`: maintains resource-name, kind, surface, build-path, owner,
  live/satisfied, and selector indexes for candidate lookup.
- `candidate_query`: returns candidate batches in bulk with stable candidate
  keys and enough diagnostic metadata for Python formatting.
- `overlay_store`: owns external slots, identifier bindings, resolved-name
  views, and single-use satisfaction state.
- `materialization_plan`: emits registered operation streams and hygiene
  streams from lower state.
- `hygiene_engine`: owns keep-name, boundary, import/export/pass, collision,
  and rename decisions once native materialization expands beyond the first
  subset.
- `artifact_builder`: produces explicit artifact copies: CPython `ast` nodes,
  rendered source, executable ASTs, and debug snapshots. It must account for
  required/default AST fields and source-location metadata.
- `snapshot_writer`: emits canonical structural snapshots matching the Python
  engine.
- `engine_selection`: selects Python or native engines at a coarse engine/scope
  boundary, never as per-record fallback.
- `packaging`: builds and loads the extension module without committing native
  build artifacts.

The existing `native_probe/` module is evidence and test scaffolding, not the
production native engine. Production native checkpoints may reuse probe code
only when the shared lower-engine contract remains unchanged.

## Checkpoint 14a: Native Decision Profile

Goal: decide whether to start native library implementation.

Status: closed by `NativeDecisionProfile.md`. The native parser/IR probe
remains viable, but the current YIDL lifecycle profile does not justify starting
`15a`-`16d`; most remaining measured time is outside Astichi lower tables.
`14b` and `14c` may proceed as boundary/skeleton work only.

Work:

- Run the Slice 13c import workload and capture a profile.
- Compare current Python lower timings against the original target.
- Attribute time to candidate lookup, occurrence/index updates,
  materialization-plan construction, hygiene, artifact construction, source
  rendering, CPython AST construction, and YIDL runtime overhead.
- Re-run native probe timings for representative Astichi/YIDL template shapes.
- Record whether native parser/IR work is justified or whether native table
  operations alone are the right first target.

Acceptance:

- The profile identifies a native-worthy Astichi lower-engine bottleneck.
- The native probe still parses, converts, copies to CPython AST, and validates
  current representative fixtures.
- A written decision says either proceed to `14b` or stop native work.

Stop if:

- Python lower meets the target.
- Remaining time is outside lower-engine work.
- CPython AST construction dominates enough that native table work cannot
  materially improve the target.

Tag: `perf-refactor/slice-14a`.

## Checkpoint 14b: Native Contract And ABI Design

Goal: define the native library boundary before implementation.

Status: closed by `EngineSelectionContract.md`. The contract now defines the
bulk native entry points, opaque handle model, request/result shapes, error
categories, external-slot ownership, parser/IR references, and feature
negotiation.

Work:

- Write or update `dev-docs/perf-refactor/EngineSelectionContract.md`.
- Define extension module entry points for engine creation, bundle
  registration, template registration, occurrence append, candidate query,
  overlay append, materialization-plan snapshot, final artifact copy, and
  teardown.
- Define native handle ownership, stale-handle errors, schema/version errors,
  and bulk result transfer shapes.
- Define how Python external values are stored as slot handles.
- Define how native parser/IR references attach to lower composables when that
  path is enabled.
- Define feature negotiation for unsupported operation primitives.

Acceptance:

- The ABI does not expose one method per Astichi surface.
- Every native call can be driven from registered handles and stable operation
  descriptors.
- Engine selection is coarse and explicit.
- Python/native parity is testable through structural snapshots and final
  goldens.

Stop if:

- The contract requires per-surface native APIs for current Astichi surfaces.
- The contract cannot represent explicit artifact-copy boundaries.

Tag: `perf-refactor/slice-14b`.

## Checkpoint 14c: Native Package Skeleton

Goal: add a loadable native extension shell without routing behavior to it.

Status: closed by the `native_engine/` skeleton and
`astichi.lower_engine.native` discovery facade. Default selection requests
`auto`, explicit build artifacts are ignored, and tests skip cleanly when the
extension has not been built. This is selection metadata only; production
lower-engine behavior is not routed to native until the extension declares the
full lower-engine capability set.

Work:

- Add the production native package skeleton and build metadata.
- Expose version, capability, and self-test functions.
- Add Python facade discovery and an engine selection override flag.
- Keep lower-engine native routing disabled until routing exists; default
  selection prefers native only when the extension is present and fully
  lower-engine capable.
- Add build artifacts to ignore rules.
- Add focused tests that skip cleanly when the extension is unavailable.

Acceptance:

- Source-only checkout remains clean after tests.
- Extension can be built locally by an explicit command.
- `auto` is the default selection policy, with Python fallback when the
  extension is absent or present but not lower-engine capable.
- Full Astichi suite passes without requiring the native extension.

Stop if:

- Packaging requires committing generated binary artifacts.
- Importing Astichi starts requiring a compiler toolchain.

Tag: `perf-refactor/slice-14c`.

## Native Lower Engine Requirement Update

The Slice 14a profile stop gate is superseded. A fully functional native lower
engine is now required, not optional. The detailed source of truth for the
remaining native implementation is `NativeLowerEngineDetailedPlan.md`.

Checkpoints 15a through 16d below remain useful as the historical coarse slice
map. The concrete native roll-build should use the finer N0 through N13 slices
from `NativeLowerEngineDetailedPlan.md`.

The important changes are:

- native parser/IR-backed template extraction is the production target;
- Python-extracted template metadata is allowed only as a parity harness input,
  not as the native success path;
- materialization and hygiene are native lower-layer responsibilities;
- native selection is capability-gated and must not treat an importable
  skeleton as a usable lower engine;
- profile measurements guide prioritization, but no longer stop native
  implementation of current Astichi/YIDL surfaces.

## Checkpoint 15a: Native Surface Registry

Goal: implement native bundle registration and handle binding.

Work:

- Implement native `surface_registry`.
- Consume the same canonical surface bundle as Python.
- Assign dynamic native surface, operation, and pattern ids.
- Reject stale handles, duplicate keys, schema mismatches, and unsupported
  operation primitives.
- Emit native registry structural snapshots matching Python.

Acceptance:

- Python and native registry snapshots match for current and dormant-future
  bundles.
- Handle misuse diagnostics match Python behavior closely enough for tests.
- Full Astichi suite passes with native tests included.

Stop if:

- Native registry needs hardcoded switches for current surfaces.

Tag: `perf-refactor/slice-15a`.

## Checkpoint 15b: Native Template Store

Goal: register Python-extracted lower templates into native tables.

Work:

- Implement native template, locator, and template-record tables.
- Import existing Python `LowerTemplateBinding` metadata into native storage.
- Rebind surface handles from stable keys into native ids.
- Store projection/debug metadata needed by snapshots.
- Emit structural snapshots matching Python for compile/template fixtures.

Acceptance:

- Native template snapshots match Python snapshots.
- No CPython AST clone is required during native template import.
- Full Astichi suite passes with native template tests.

Stop if:

- Template registration needs Python `Inventory` projection after compile-time
  extraction.

Tag: `perf-refactor/slice-15b`.

## Checkpoint 15c: Native Occurrences And Indexes

Goal: implement native occurrence/state/index tables.

Work:

- Append root/source occurrences natively.
- Derive record handles from `(OccurrenceId, TemplateRecordId)`.
- Maintain live/dead/satisfied state.
- Maintain resource-name, kind, surface, owner, build-path, and name-kind
  indexes.
- Emit structural snapshots matching Python scope fixtures.

Acceptance:

- Native lower state snapshots match Python for add/apply fixtures.
- Appending an occurrence is O(records in template), not O(total scope
  records).
- Full Astichi suite passes with native state tests.

Stop if:

- Index maintenance requires Python callbacks per record.

Tag: `perf-refactor/slice-15c`.

## Checkpoint 15d: Native Candidate Query

Goal: query native indexes and return candidate batches in bulk.

Work:

- Implement native candidate lookup for composable, external-value, and
  identifier resources.
- Evaluate registered compatibility descriptors natively.
- Preserve resolved-name lookup for identifier overlays.
- Return stable candidate keys plus lazy diagnostic metadata.
- Keep Python candidate adapters only as facade wrappers.

Acceptance:

- Candidate results match Python lower lookup for migrated fixtures.
- Candidate lookup does not call debug inventory projection.
- Missing/ambiguous diagnostics stay useful.
- Full Astichi suite passes with native candidate tests.

Stop if:

- Diagnostics require constructing Python `InventoryRecord` objects on every
  candidate.

Tag: `perf-refactor/slice-15d`.

## Checkpoint 15e: Native Overlay Store

Goal: route external and identifier overlays through native state.

Work:

- Implement native external slot allocation.
- Implement native identifier overlay storage and resolved-name views.
- Mark single-use demands satisfied natively.
- Transfer external Python objects by slot handle, not by embedding them in
  native-owned copies.
- Snapshot overlays matching Python.

Acceptance:

- External and identifier overlay snapshots match Python.
- Candidate lookup sees resolved owner/name selectors.
- Full Astichi suite passes with native overlay tests.

Stop if:

- External value lifetime cannot be made explicit at the engine boundary.

Tag: `perf-refactor/slice-15e`.

## Checkpoint 15f: Native Parser/IR Integration

Goal: integrate native parser/IR for template registration.

Work:

- Use the native probe results as the production parser/IR starting point.
- Parse source text natively and attach native AST/IR references to template
  records.
- Use Python-extracted template metadata only as a parity harness oracle.
- Keep CPython AST/source as explicit artifact-copy outputs.
- Validate grammar/version coverage against current fixture sources.

Acceptance:

- Native parser/IR registration matches Python template snapshots for selected
  fixtures.
- Native-selected `astichi.compile(...)` does not use Python `ast.parse(...)`
  or Python `Inventory` extraction on the success path.
- Full Astichi suite passes.

Stop if:

- Parser grammar gaps break current supported Python versions.
- Parser/IR integration needs CPython internal compiler APIs.

Tag: `perf-refactor/slice-15f`.

## Checkpoint 16a: Native Materialization Plan

Goal: emit materialization and hygiene streams natively.

Work:

- Implement native materialization-plan construction for the Python Slice 11
  subset.
- Emit registered operation ids and stable operation keys.
- Emit hygiene stream placeholders and overlay operations.
- Match Python structural materialization snapshots.

Acceptance:

- Native and Python materialization-plan snapshots match.
- No per-operation Python callback is needed.
- Full Astichi suite passes with native plan tests.

Stop if:

- A plan operation requires surface-specific native API expansion.

Tag: `perf-refactor/slice-16a`.

## Checkpoint 16b: Native Artifact Builder

Goal: construct final artifacts from native materialization state.

Work:

- Build CPython AST artifacts at the explicit final boundary.
- Populate required/default fields and location metadata deliberately.
- Optionally render source when the selected backend supports it.
- Measure artifact construction, location population, `compile(...)`, and
  optional `exec(...)` separately.
- Treat constructor warnings or missing fields as compatibility failures.

Acceptance:

- Native artifact output matches Python final goldens for the supported subset.
- `compile(...)` accepts copied CPython AST nodes.
- Full Astichi suite passes with native artifact tests.

Stop if:

- CPython AST construction cost erases the native win and there is no
  alternative artifact boundary.

Tag: `perf-refactor/slice-16b`.

## Checkpoint 16c: Native Full Surface Expansion

Goal: expand native materialization/hygiene to every current Astichi/YIDL
surface.

Work:

- Add native support for parameters, elif, defaulted holes, pyimport, boundary
  pass/import/export, keep-name, and collision rename in the same order as the
  Python checkpoints.
- Keep operation-stream driven implementation; do not add one native entry
  point per surface.
- Match Python structural and final goldens after each surface family.

Acceptance:

- Native structural snapshots match Python.
- Native final-output goldens match Python for every enabled surface family.
- Full Astichi suite passes with native enabled for covered fixtures.

Stop if:

- A current surface cannot be represented by registered pattern templates and
  operation primitives without adding a per-surface native public API.

Tag: `perf-refactor/slice-16c`.

## Checkpoint 16d: Native Profile And Engine Selection

Goal: close native implementation with measured engine-selection behavior.

Work:

- Run Python and native engines against the import workload.
- Compare candidate lookup, overlays, materialization plan, hygiene, artifact
  copy, source rendering, CPython AST construction, and final compile/exec
  timings.
- Make `auto` select native by default only when native declares the full
  lower-engine capability set and passes the workload gate.
- Document fallback policy and unsupported-operation diagnostics.

Acceptance:

- Native engine is a complete selectable implementation for current surfaces.
- Engine selection is coarse and deterministic.
- Full Astichi suite passes in the selected default configuration.

Stop if:

- Native cannot pass the current structural, final, and YIDL verification
  gates.

Tag: `perf-refactor/slice-16d`.

## Verification Matrix

Every checkpoint:

```text
uv run --with pytest pytest <focused tests> -q
uv run --with pytest pytest -q
```

Additional gates when touched:

- YIDL runtime/caller migration: run available YIDL generation/runtime tests.
- Structural snapshot changes: write actual structural output and compare
  checked-in goldens.
- Final materialization changes: run affected final-output goldens.
- Counter/profile changes: run the focused perf-counter test and the import
  workload.

## Roll-Build Stop Points

Stop and patch design before continuing when:

- a lower materialization operation cannot express a current surface;
- candidate lookup needs debug `Inventory` projection on a success path;
- hygiene decisions cannot be represented in `hygiene_stream`;
- a checkpoint would leave YIDL green only through an uncounted adapter path;
- full-suite success requires duplicating broad success assertions outside the
  golden harness.
