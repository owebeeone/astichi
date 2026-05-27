# Astichi Perf Refactor Detailed Design Set

Status: detailed design draft.

This directory expands `dev-docs/AstichiPerfRefactorProposal.md` into the
implementation design and sliced build plan for the inventory-first assembly
refactor.

The proposal remains the rationale document. These documents are the working
design artifacts for implementation planning:

- `StructuralInventoryDesign.md`: shared inventory model, Python reference data
  structures, native backing data structures, handle ownership, and snapshot
  shape.
- `BuildOperationsAnalysis.md`: add/apply/candidate/materialization operations,
  hot-path complexity, Python behavior, native behavior, and counters.
- `SurfaceExtensionContract.md`: dynamic surface registration, shared
  AST-pattern/operation descriptors, and the contract for adding future Python
  syntax surfaces without rebuilding the lower-engine API. It also contains the
  current Astichi pattern inventory that the registry must cover.
- `VerificationAndGoldens.md`: structural snapshot round trip, golden layout,
  success-path coverage policy, and which bespoke tests remain appropriate.
- `AssemblyApiLedger.md`: Slice 0 API audit ledger for required, adapter-only,
  validation-only, and removable assembly APIs.
- `SnapshotGrammar.md`: Slice 2 mini-spec for canonical structural snapshot
  shape and round-trip behavior.
- `LowerTemplatePackageV2.md`: behavior-complete lower-template package
  contract for records, locators, scopes, markers, managed imports, and dense
  runtime encoding.
- `PythonLowerTemplatePackageV2Plan.md`: Python-first roll-build plan to make
  the reference lower engine produce and consume the v2 package before native
  hygiene parity work.
- `EngineSelectionContract.md`: native-engine selection and compatibility gate
  for the production native lower engine.
- `NativeAstProbe.md`: parallel proof-of-concept plan for a native parser and
  final CPython AST emitter.
- `NativeDecisionProfile.md`: Slice 14a profile record. It is historical
  context, not a stop gate for the now-required native lower engine.
- `NativeLowerEngineDetailedPlan.md`: required implementation plan for the
  fully native lower engine, including data structures, facade integration,
  verification, and roll-build slices.
- `NativePerformancePlan.md`: roll-build plan for turning the now-selectable
  native lower-engine path from a correct hybrid path into a faster
  native-authoritative path.
- `FullSelfNativeRustAstPlan.md`: self-native boundary (Rust until single
  `copy_python_ast` handoff); `native.self_native.*` capabilities; tags
  `perf-native-full/*`; supersedes hybrid P7 closeout for this track.
- `SlicedBuildPlan.md`: commit-sized implementation slices, including API
  pruning before lower-engine changes.

## Design Commitments

- Inventory is the authoritative assembly state after `AssemblyScope.add(...)`.
- The Python facade adapts inputs and outputs; it does not own candidate
  lookup, inventory merge, materialization, or hygiene.
- The first engine is Python, using the same lower-engine API as the production
  native implementation.
- The production native engine is required. It is not considered complete until
  native compile, template extraction, scope state, candidate lookup, overlays,
  materialization, hygiene, and final artifact copy all pass the shared golden
  harness.
- `astichi.compile(...)` should register lower templates and return a
  lower-backed composable facade. CPython AST/source extraction is an explicit
  artifact-copy path for tests, output, and compatibility.
- C++ is not mandatory. The native requirement is a compiler path that can keep
  parse, transform, materialization, and hygiene work below the Python object
  boundary until final artifact creation.
- The default final artifact boundary is public CPython `ast`/`_ast`
  construction plus public `compile(...)`; internal CPython compiler APIs need a
  separate spike and acceptance gate.
- Materialization and hygiene are lower-layer responsibilities from the start.
- Data required by materialization, hygiene, diagnostics, or final output must
  be part of the lower-template package contract. Private engine metadata may
  only cache or index package/state facts.
- Successful end-to-end behavior is validated through canonical goldens and
  structural snapshots, not duplicated bespoke tests.
- Printing or projecting inventory is diagnostic/debug behavior and may be
  slower than the hot path.
- Future syntax surfaces register semantic specs and operation descriptors.
  The lower-engine API should not grow one method per surface.
- Likely future syntax surfaces should have dormant pattern templates in the
  registry so they can be enabled later without rebuilding native code when
  they use existing operation primitives.

## Slice Gates Still To Finalize

The proposal is detailed enough to start Slice 0 and Slice 1. These remaining
decisions are now assigned to named slice deliverables:

- Slice 0 owns the obsolete assembly API list through
  `AssemblyApiLedger.md`.
- Slice 2 owns the exact structural snapshot grammar and regeneration command
  through `SnapshotGrammar.md`.
- Slice 3 confirms the concrete Python module boundary proposed in
  `StructuralInventoryDesign.md`.
- Slice 4a owns the exact surface bundle grammar, handle-binding policy, and
  signature/version policy for serialized or cached representations.
- Slice 7b moved YIDL and Astichi success-path lookup to
  `AssemblyScope.find_candidates(...)`; standalone
  inventory lookup is now the private debug helper
  `find_candidates_in_inventory(...)`.
- Slice 14 owns the test-visible native engine selection spelling through
  `EngineSelectionContract.md`.
- Slice 16 decides whether native materialization emits Python `_ast` objects
  directly or a validated artifact for the facade to consume.
- Native N9b2 depends on `LowerTemplatePackageV2.md`; it is a lower-engine API
  contract slice, not a native-private metadata patch.
- `PythonLowerTemplatePackageV2Plan.md` must complete at least through P5d
  before native N9b3 can honestly claim full marker/import/hygiene ownership.
- `NativeLowerEngineDetailedPlan.md` supersedes the historical native stop
  gates from Slice 14. The native probe result is accepted as sufficient
  evidence to pursue native parsing plus final CPython AST construction as the
  production backend shape.

Those are slice gates, not reasons to keep expanding the proposal.
