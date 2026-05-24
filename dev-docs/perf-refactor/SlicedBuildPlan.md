# Sliced Build Plan

Status: detailed design draft.

This plan breaks the inventory-first refactor into implementation slices. Each
slice should be small enough to review independently and should preserve a
working tree with focused verification.

No lower-engine implementation slice should start before API pruning has
reduced the assembly surface.

## Slice 0: Assembly API Surface Audit And Pruning

Goal: remove or quarantine unused assembly APIs before new lower-engine code
depends on them.

Work:

- audit uses of `astichi.assembler.scope`, builder handles, and composable bind
  surfaces in Astichi and YIDL;
- classify each surface as required hot path, required final-output path,
  validation-only, adapter-only, or removable;
- record the classification in `dev-docs/perf-refactor/AssemblyApiLedger.md`;
- update YIDL callers where a smaller scope API is clearer;
- remove tests that only preserve obsolete API shape;
- keep behavior coverage through existing final goldens or new structural
  goldens.

Acceptance:

- supported assembly API surface is documented;
- `AssemblyApiLedger.md` names every audited API surface, caller, replacement,
  and removal/adaptation decision;
- unused APIs are removed or explicitly marked adapter-only;
- no lower-engine design requires preserving obsolete public shape;
- Astichi and YIDL success-path goldens still pass for affected cases.

Stop if:

- an apparently unused API is needed by YIDL generated output;
- removing an API changes behavior not covered by a golden.

## Slice 1: Baseline Counters

Goal: make current hot-path costs visible without cProfile.

Work:

- add counters around `AssemblyScope.apply`;
- count `_rebuild_composable`;
- count `_replace_occurrence_inventory`;
- count candidate lookup and inventory projection;
- count materialization and executable AST conversion;
- add an import workload command for the 8-class lifecycle case.

Acceptance:

- focused command reports counts and timings;
- baseline matches the profile shape in `dev-docs/AstichiPerfAnal.md`;
- counters do not materially change behavior.

Golden policy:

- no new success-path bespoke tests;
- use a narrow counter test only to prove counters can be collected.

## Slice 2: Structural Snapshot Harness

Goal: create the canonical intermediate verification path before replacing the
intermediate representation.

Work:

- define snapshot writer and reader;
- finalize the mini grammar in `dev-docs/perf-refactor/SnapshotGrammar.md`;
- add `tests/data/goldens/structural/`;
- extend actual-output directories with structural output;
- add round-trip check for snapshot text;
- add initial structural fixtures for small assembly cases.

Acceptance:

- structural snapshot round trip is deterministic;
- snapshot text follows `SnapshotGrammar.md`;
- structural goldens do not contain absolute paths or Python repr addresses;
- existing pre-materialized and materialized goldens still pass;
- successful intermediate behavior is represented by goldens, not broad bespoke
  tests.

Stop if:

- the snapshot cannot represent materialization or hygiene decisions needed by
  the proposal.

## Slice 3: Python Lower Engine Skeleton

Goal: introduce the internal lower-engine module and handle types without
routing production code through it yet.

Work:

- add `src/astichi/lower_engine/`;
- confirm the module boundary proposed in
  `dev-docs/perf-refactor/StructuralInventoryDesign.md`;
- define handles and table owners;
- define template, occurrence, edge, overlay, index, snapshot, and
  materialization-plan objects;
- add a private engine object used only by tests/fixtures.

Acceptance:

- no public behavior changes;
- structural snapshot for a manually built tiny state is golden-covered;
- no new fixed public category API is introduced.

Golden policy:

- success path uses structural fixture output;
- bespoke tests only cover invalid handle misuse and snapshot parser errors.

## Slice 4a: Surface Registry Shell And Handle Binding

Goal: make the registry/bundle/handle mechanics real without migrating current
pattern scanners yet.

Work:

- define the internal surface spec classes;
- define the canonical surface bundle shape consumed by Python and native
  engines;
- define stable surface, pattern, and operation keys for snapshots;
- assign dynamic `SurfaceId`, `OperationId`, and `PatternId` handles at
  registration time;
- store returned handles on the registered Python surface, operation, and
  pattern specs;
- define the initial operation primitive vocabulary as keys plus one-paragraph
  semantics, without executable behavior;
- define compatibility-rule shape, including structural shape predicates and
  result-policy objects;
- compile registered `shape_predicate` semantic objects into compact
  `ShapePredicateDescriptor` data for hot-path/native compatibility checks;
- snapshot a minimal bundle catalog through structural goldens.

Acceptance:

- a minimal bundle can register and return handles;
- stale or wrong-engine handles are rejected;
- structural snapshots write stable keys, not only dynamic ids;
- candidate compatibility can ask the registry whether a production surface
  satisfies a target surface through a registered rule;
- native compatibility checks can evaluate shape descriptors without
  per-candidate Python callbacks;
- native API design remains generic and does not add one method per surface.

Stop if:

- handle binding cannot prove that Python specs and engine tables refer to the
  same registered bundle;
- compatibility requires hardcoded core switches before current scanners are
  migrated.

Golden policy:

- successful minimal registry output is covered by structural goldens;
- operation vocabulary goldens cover catalog keys and short semantics only;
- bespoke tests cover duplicate registration, stale/wrong-engine handles,
  stale serialized bundle signatures/schema mismatches, and unsupported-operation
  diagnostics.

## Slice 4b: Current Pattern Consolidation

Goal: map every current Astichi pattern onto registered pattern templates or an
explicit temporary adapter.

Work:

- enumerate every current Astichi authored, internal, emitted, reserved, and
  diagnostic-only pattern in the registry catalog;
- consolidate current pattern recognition into reusable pattern templates such
  as direct call, statement prefix, decorator call, definition name, identifier
  suffix, defaulted `with`, payload expression, payload function, sentinel
  attribute, loop unroll, and internal metadata;
- register existing surfaces: block, expression, parameter, funcargs, elif,
  external value, identifier, pyimport, boundary pass/import/export, and
  hygiene-related marker surfaces;
- record any temporary scanner adapters and their removal slices;
- add registry catalog structural goldens.

Acceptance:

- every current pattern in `SurfaceExtensionContract.md` maps to exactly one
  registered pattern spec or a deliberate diagnostic-only spec;
- existing marker/payload/prefix recognizers are implemented through shared
  pattern templates or explicitly listed as temporary migration adapters;
- overlapping scanners have an explicit registry policy;
- template records can refer to registered surface ids.

Stop if:

- current surfaces cannot be represented without hardcoded core switches;
- two current scanners classify the same AST shape differently without a policy
  in the registry.

Golden policy:

- successful registry catalog output is covered by structural goldens;
- bespoke tests cover scanner conflicts and unsupported scanner shapes.

## Slice 4c: Dormant Future Templates And Extension Stub

Goal: prove likely future syntax surfaces can be registered without changing
the core lower-engine API when they use existing operation primitives.

Work:

- add dormant/proposed pattern templates for likely future surfaces such as
  match/case, exception handlers, loop `else`, try `else`, try `finally`, and
  with-item insertion;
- keep dormant templates inactive so they do not recognize authored source or
  produce records;
- add one extension-surface fixture or design stub to prove the registry can
  accept a future surface without changing core engine APIs;
- collect any native AST probe feedback that suggests operation keys or
  operation captures are awkward against a non-CPython AST/IR;
- snapshot dormant template catalog entries.

Acceptance:

- dormant future templates can register, receive handles, and appear in the
  bundle catalog without affecting current behavior;
- the operation vocabulary can express likely match/case, exception-handler,
  and loop-else surfaces, or it clearly names the primitive gap;
- native calls after registration use handles returned by that registration
  step;
- native probe vocabulary concerns are either patched into the operation catalog
  or explicitly deferred before Slice 4c closes.

Stop if:

- likely future surfaces need a new primitive before current patterns can be
  migrated;
- dormant templates make current recognition ambiguous.

Golden policy:

- dormant template registration is covered by structural goldens;
- bespoke tests cover disabled-surface diagnostics only.

## Slice 5: Template Registration And Index Metadata

Goal: register composable templates into lower-engine records.

Implementation split:

- Slice 5a registers compile/rebuild inventory metadata as lower templates and
  stores an internal lower binding on `BasicComposable`. This is metadata-only:
  it proves template record lowering, current surface-bundle registration, and
  dynamic surface handles without routing `AssemblyScope` yet.
- Slice 5b completes the template-registration handoff needed by later scope
  slices: reusable destination-engine template import/deduplication and
  explicit artifact-copy boundaries for facade tests. Derived occurrence
  indexes and candidate lookup move in Slices 6 and 7.

Work:

- lower existing `Inventory` extraction into template records;
- route `astichi.compile(...)` through the lower module so it returns a facade
  composable backed by a lower `TemplateId`;
- define explicit artifact-copy APIs for copied CPython AST nodes, rendered
  source, and executable AST output;
- migrate tests that assert the old `astichi.compile(...)` return shape to
  structural goldens or explicit artifact-copy APIs;
- attach registered surface ids to target and production records;
- precompute target indexes, scope indexes, and locator ids;
- implement the source locator scheme from
  `dev-docs/perf-refactor/StructuralInventoryDesign.md`;
- intern symbol names and build-path segments;
- snapshot template metadata.

Acceptance:

- `astichi.compile(...)` produces a lower-backed composable facade;
- normal assembly consumes lower template/composable handles, not copied
  CPython AST nodes;
- copied AST/source artifact APIs are available for existing tests and goldens;
- known return-shape churn from `astichi.compile(...)` is documented in
  `AssemblyApiLedger.md` and `AstichiSingleSourceSummary.md`;
- existing golden fixtures can emit template sections in structural snapshots;
- template registration scans AST once per template;
- no candidate lookup path needs Python `Inventory` projection.

Stop if:

- template records lose metadata needed by parameter holes, elif targets,
  pyimports, or hygiene.

## Slice 6: Occurrence And Structural Inventory State

Goal: add root/source occurrences and expose derived records through lower
indexes.

Work:

- append occurrences from template ids;
- derive `RecordId = (OccurrenceId, TemplateRecordId)`;
- maintain live/satisfied record state;
- update resource, hole, identifier, external, production, build-path, and
  owner indexes;
- project debug `Inventory` from lower state only on request.

Acceptance:

- structural snapshots cover occurrences and live records;
- projected `scope.inventory` matches existing expectations for selected
  compatibility cases;
- no full Python `Inventory` object is built during candidate lookup in lower
  tests.

Golden policy:

- successful inventory shape is structural golden output;
- bespoke tests only cover projection mechanics too small for fixtures.

## Slice 7: Lower Candidate Lookup

Goal: make `find_candidates` work against lower indexes.

Work:

- lower resource descriptors for composable, external value, and identifier
  resources;
- query lower indexes directly;
- use registry compatibility rules for syntax target/production matching;
- produce stable candidate handles/keys;
- preserve diagnostics through lazy formatting;
- support same-site binding collapse used by YIDL.

Acceptance:

- candidate lookup does not project `Inventory`;
- ambiguous/missing diagnostics stay useful;
- structural snapshots show selected candidate keys where useful;
- focused scope fixtures use lower lookup.

Golden policy:

- success candidate behavior appears in structural fixtures;
- bespoke tests cover missing and ambiguous diagnostics.

## Slice 7.5: Transient Differential Harness

Goal: catch semantic drift while legacy assembly and lower assembly can still
run side by side.

Work:

- add a constrained generator for small composable graphs;
- cover block holes, expression inserts, identifier binds, external binds, and
  single-add satisfaction first;
- run the same generated structure through the legacy assembler and the lower
  engine;
- compare projected inventory where both engines expose one;
- compare final source or AST for supported materialized cases;
- record seed/minimized fixture data for mismatches.
- expand the generator grammar in lockstep with Slice 12 surfaces before the
  harness is retired.

Acceptance:

- the harness can run as an opt-in verification command;
- failures point to a reproducible fixture or seed;
- the harness is clearly marked transient and does not replace golden success
  coverage.
- before Slice 13 cleanup, the harness has covered every surface moved in
  Slices 12a, 12b, and 12c.

Golden policy:

- no generated success-path assertions are checked in as bespoke tests unless
  they become named golden fixtures;
- mismatches that expose real drift are reduced into structural or final-output
  goldens.

## Parallel Track A: Native AST Parser And Emitter Probe

Goal: decide whether the later native backend should parse and transform a
native AST/IR, then instantiate CPython AST nodes only at the final artifact
boundary.

This track can run in parallel with the main Python lower-engine slices. It does
not block Slice 0 through Slice 13 unless it exposes a design constraint that
changes the shared lower-engine contract.

Work:

- follow `dev-docs/perf-refactor/NativeAstProbe.md`;
- build a small native Python module using `ruff_python_parser`,
  `rustpython-parser`, or another justified native parser;
- parse source text into a native AST or normalized Astichi AST IR;
- wrap the native tree in the common lower composable facade backed by the
  native engine;
- copy the lower composable into real CPython `ast`/`_ast` nodes only through an
  explicit artifact API;
- optionally render source from the lower composable for parity tests;
- call `compile(...)` on the returned AST and `exec(...)` the resulting code in
  a smoke test;
- run `ast.parse(...) + minimal Python scan` as the required baseline for every
  measured input;
- measure native parse time, native conversion time, CPython AST node
  construction time, lower composable wrapper construction time,
  artifact-copy time, required/default field population time, location metadata
  population time, optional `ast.fix_missing_locations(...)` time,
  `compile(...)` time, and optional `exec(...)` time;
- keep the default artifact boundary on public `ast`/`_ast` construction plus
  public `compile(...)`;
- remove general-purpose `compile_module(...)` / `exec_module(...)` APIs from
  the probe surface; `compile(...)` and `exec(...)` belong to the test harness;
- report vocabulary/operation-stream concerns by the end of Slice 4c and
  artifact-construction metadata concerns by the end of Slice 11;
- test representative Astichi/YIDL template shapes before attempting full
  Astichi semantics.

Acceptance:

- the native module can return the common lower composable facade backed by
  native storage;
- the native module can return a CPython AST module that `compile(...)` accepts;
- the compiled code can execute through `exec(...)`;
- timings include `ast.parse(...) + minimal Python scan` for the same input;
- timings separate parse, convert, lower composable wrapping, CPython AST
  construction, artifact copy, required/default field population, location
  population, compile, and exec;
- the probe identifies grammar/version gaps and source-location requirements;
- the probe does not require internal CPython compiler APIs;
- the probe documents whether the native path is at least 5x faster than the
  baseline on representative YIDL lifecycle-shaped templates, or explains the
  non-timing reason to keep investigating it;
- the result is documented before Slice 14 chooses a native backend direction.

Stop if:

- the parser cannot track Astichi's supported Python grammar versions;
- CPython AST node construction dominates enough to erase native parse/transform
  gains;
- source-location or validation gaps make generated ASTs unsuitable for current
  goldens and diagnostics;
- the probe requires `PyArena`, `_PyAST_Compile`, or other internal CPython APIs
  before it can prove basic parse-to-`compile(...)` viability.

## Slice 8: Route `AssemblyScope.add` Through Lower Engine

Goal: make lower state authoritative after root add.

Work:

- initialize lower state in `AssemblyScope`;
- register templates on add;
- append root occurrences;
- keep builder graph only as a temporary build adapter if still needed;
- route `scope.inventory` through debug projection;
- update `dev-docs/AstichiSingleSourceSummary.md` for behavior changed in this
  slice.

Acceptance:

- existing scope tests pass after being converted where appropriate;
- structural goldens cover add state;
- no lower-engine prototype depends on obsolete API shape.

## Slice 9: Route `AssemblyScope.apply` For Composable Inserts

Goal: remove per-apply composable rebuild and inventory replacement for
composable insertion.

Work:

- append source occurrences and edges;
- mark single-add holes satisfied;
- update lower indexes incrementally;
- preserve target/ref-path diagnostics;
- measure adapter cost separately if `scope.build()` still bridges to legacy
  materialization;
- update `dev-docs/AstichiSingleSourceSummary.md` for behavior changed in this
  slice.

Acceptance:

- counters show zero `_replace_occurrence_inventory` calls on the scope apply
  hot path;
- counters show no per-apply AST clone/rebuild for composable inserts;
- YIDL lifecycle import still produces equivalent classes;
- structural goldens replace tests that asserted old intermediate AST shape.

## Slice 10: Route External And Identifier Applies As Overlays

Goal: stop eager `BasicComposable.bind` and `bind_identifier` during scope
assembly.

Work:

- add lower overlay bindings;
- maintain external object slots in the facade;
- mark satisfied demands correctly;
- preserve duplicate/rebind diagnostics;
- expose overlay state in structural snapshots;
- update `dev-docs/AstichiSingleSourceSummary.md` for behavior changed in this
  slice.

Acceptance:

- counters show zero `_rebuild_composable` calls for these scope applies;
- identifier/external success behavior is golden-covered;
- diagnostics remain covered by focused bespoke tests.

## Slice 11: Lower-Owned Materialization Subset

Goal: make `scope.build()` consume lower state for the first supported subset.

Work:

- produce materialization plans from lower occurrences, edges, and overlays;
- emit operation streams using registered operation ids;
- emit a canonical `hygiene_stream` for hygiene decisions, even when the first
  supported subset is small;
- materialize simple block insertion, expression insertion, external bind, and
  identifier bind through the lower materialization API;
- incorporate native AST probe feedback about artifact-construction metadata
  required by CPython AST emission;
- snapshot materialization plans;
- keep final materialized output equivalent;
- update `dev-docs/AstichiSingleSourceSummary.md` for behavior changed in this
  slice.

Acceptance:

- materialization and hygiene API ownership is lower-layer;
- structural materialization snapshots round trip;
- materialization snapshots include both `operation_stream` and
  `hygiene_stream`;
- final output goldens pass for supported cases;
- any legacy build adapter cost is counted and visible.

Stop if:

- the lower plan cannot express an existing marker family without redesign.

## Slice 12a: Parameters And Elif Materialization

Goal: move parameter holes and elif targets onto lower-owned operation streams.

Work:

- add parameter-hole materialization;
- add elif-target materialization;
- extend the transient differential harness with parameter-hole and elif
  generators;
- snapshot operation streams for both surfaces;
- update affected final-output goldens;
- update `dev-docs/AstichiSingleSourceSummary.md` for behavior changed in this
  slice.

Acceptance:

- parameter-hole and elif final-output goldens pass;
- structural materialization goldens cover parameter and elif operations;
- facade does not reconstruct parameter or elif intent from Python
  `Inventory`.

## Slice 12b: Defaulted Holes And Pyimport Materialization

Goal: move defaulted block holes and managed pyimports onto lower-owned
materialization/hygiene operations.

Work:

- add defaulted block-hole materialization;
- add pyimport placement and validation;
- extend the transient differential harness with defaulted-hole and pyimport
  generators;
- snapshot fallback/default and managed-import decisions;
- update affected final-output goldens;
- update `dev-docs/AstichiSingleSourceSummary.md` for behavior changed in this
  slice.

Acceptance:

- defaulted-hole and pyimport final-output goldens pass;
- structural materialization/hygiene goldens cover default selection and import
  placement;
- facade does not reconstruct default or pyimport intent from Python
  `Inventory`.

## Slice 12c: Boundary And Hygiene Materialization

Goal: move boundary pass/import/export, keep-name, and collision rename
decisions onto lower-owned hygiene operations.

Work:

- add boundary pass/import/export handling;
- add keep-name and collision rename decisions;
- extend the transient differential harness with boundary and hygiene cases;
- remove facade-driven materialization from the hot path;
- update affected final-output goldens;
- update `dev-docs/AstichiSingleSourceSummary.md` for behavior changed in this
  slice.

Acceptance:

- all existing Astichi final-output goldens pass;
- structural materialization/hygiene goldens cover boundary and hygiene marker
  families;
- materialization call count and AST traversal count drop;
- facade does not reconstruct intent from Python `Inventory`.

## Slice 13: Adapter Cleanup And API Tightening

Goal: remove temporary bridge code and unsupported assembly surfaces.

Work:

- delete legacy builder-state mutations from `AssemblyScope.apply`;
- remove temporary build-only adapters if lower materialization is complete;
- update `dev-docs/AstichiSingleSourceSummary.md` with current behavior;
- retire counters whose target legacy paths no longer exist;
- simplify YIDL callers to the supported lower-scope API.

Acceptance:

- no adapter cost appears in the YIDL import profile;
- supported API surface is smaller than the starting surface;
- dead migration counters are removed or quarantined with a clear owner;
- obsolete tests are removed or replaced by goldens.

## Slice 14: Native Compiler Spike Gate

Goal: decide whether native implementation is still justified and which native
shape to pursue.

Work:

- profile Python lower engine after Slice 13;
- identify remaining time in inventory, matching, materialization, or hygiene;
- review the native AST parser/emitter probe results;
- decide whether the native backend should be Rust, C++, or a hybrid module;
- decide whether native code uses a native parser/AST IR or only lower-engine
  tables plus final artifact emission;
- confirm the native backend can use the same structural snapshots and final
  goldens;
- define native extension lifetime and engine-selection behavior;
- finalize `dev-docs/perf-refactor/EngineSelectionContract.md`.

Acceptance to proceed:

- Python lower engine is functionally complete for the YIDL hot path;
- 8-class lifecycle workload remains above the intermediate budget;
- remaining profile points at lower-engine work, not facade or test overhead;
- structural snapshots are stable enough for engine parity testing;
- native AST probe results are documented, including parse, convert, CPython AST
  construction, artifact-copy, required/default field population, location
  population, source-rendering, compile, and exec timings;
- native AST probe results include the `ast.parse(...) + minimal Python scan`
  baseline for the same inputs;
- native parser plus the selected fallback policy can run current
  `tests/data/gold_src/` fixtures;
- native backend selection does not depend on internal CPython compiler APIs
  unless a separate spike has proved and accepted that maintenance cost;
- engine selection is a coarse scope/engine decision, not per-record fallback.

Stop if:

- Python lower engine meets the import-time target;
- remaining time is in YIDL no-op edge evaluation or unrelated code;
- the only viable native path depends on internal CPython compiler APIs and no
  separate spike has accepted that dependency.

## Slice 15: Native Lower Engine Prototype

Goal: implement the same lower-engine contract natively for the measured hot
path.

Work:

- consume the same registered surface bundle as the Python engine;
- implement native tables for templates, occurrences, records, indexes,
  overlays, and snapshots;
- make native `astichi.compile(...)` registration use the native parser and
  return the common lower composable facade;
- expose opaque engine/state handles to Python;
- transfer candidates and snapshots in bulk;
- reuse Python semantic extraction initially unless profiling requires native
  extraction;
- if the native AST probe justifies it, parse source text into a native AST or
  normalized Astichi AST IR instead of using CPython AST objects as the working
  graph;
- keep CPython AST/source conversion as explicit artifact-copy operations;
- run Python and native engines against the same structural and final goldens.

Acceptance:

- same goldens pass against both engines;
- structural snapshots match;
- lower composables backed by native storage can copy to CPython AST/source for
  compatibility tests;
- Python facade code is unchanged except for engine selection;
- profile shows Python time has moved out of inventory merge, candidate lookup,
  materialization, and hygiene.

## Slice 16: Native Materialization And Hygiene Expansion

Goal: move the remaining hard lower-layer work into native code only if needed.

Work:

- implement materialization-plan construction natively;
- consume registered operation streams rather than adding one native API call per
  surface;
- implement hygiene decision tables natively or through generated semantic
  tables with signature/version validation;
- perform AST transforms against native tables/native AST IR rather than
  CPython AST objects when the native parser/emitter probe justifies that path;
- construct Python `_ast` objects in bulk only at the final materialized
  artifact boundary, or emit a validated artifact accepted by the facade;
- populate required/default fields and location metadata deliberately, with
  constructor warnings treated as compatibility failures;
- keep external Python object access slot-based.

Acceptance:

- materialization/hygiene structural snapshots match Python engine output;
- final Astichi and YIDL goldens pass;
- per-record Python boundary chatter is absent from profiles.
