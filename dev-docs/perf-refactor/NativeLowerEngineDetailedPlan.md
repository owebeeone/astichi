# Native Lower Engine Detailed Plan

Status: required implementation plan.

The native probe proved the important boundary question: native code can parse
Python source, keep a native tree as the working representation, copy public
CPython `ast`/`_ast` nodes at the final artifact boundary, and validate those
nodes with public `compile(...)`. This plan turns that proof into a fully
functional Astichi lower engine.

The implementation target is not an optional micro-optimization. Native is a
complete lower-engine implementation behind the same facade as the Python
reference engine.

## Definition Of Done

A fully functional native lower engine means:

- `astichi.compile(...)`, when native is selected, sends source text and compile
  origin to the native module and receives a native-backed composable facade.
- Template extraction uses the registered native pattern system and native
  parser/IR. It does not build Python `ast` nodes or Python `Inventory` objects
  on the success path.
- `AssemblyScope.add(...)`, candidate lookup, apply, external binding,
  identifier binding, overlay storage, materialization planning, and hygiene
  all operate on native handles and native tables.
- Python facade objects only adapt public Astichi/YIDL-facing APIs, own Python
  external-value references, format diagnostics, and request explicit artifact
  copies for goldens or runtime output.
- Final artifacts cross back to Python only at explicit boundaries:
  `copy_python_ast`, optional `render_source`, and public `compile(...)`.
- Structural snapshots and final goldens pass for the same fixture set as the
  Python lower engine.
- Native selection is capability-gated. A skeleton extension that only imports
  must not be selected as the native lower engine.

The Python lower engine remains the correctness oracle until native parity is
closed. It is not a per-record fallback once a native scope starts.

## Current Gap

The current native pieces are useful but incomplete:

- `native_probe/` proves parser and artifact viability.
- `native_engine/` is only a production extension skeleton with version,
  capability, and self-test functions.
- `src/astichi/lower_engine/native.py` currently owns discovery and selection
  metadata, not native lower behavior.
- `src/astichi/lower_engine/engine.py` is the Python reference state machine.
- `src/astichi/lower_engine/facade.py` still imports Python-extracted inventory
  metadata into lower templates.

The missing work is the Astichi-specific lower state machine: surface bundle
registration, pattern extraction, template records, occurrence indexes,
candidate query, overlays, materialization/hygiene, artifact construction, and
facade routing.

## Architecture

Native owns the hot lower-layer data structures. Python owns the facade.

```text
Python source
  -> astichi.compile(...)
  -> native parser
  -> native AST/IR
  -> registered pattern extraction
  -> native template store
  -> NativeComposable facade
  -> AssemblyScope native state
  -> native candidate query/apply/overlay/hygiene/materialization
  -> explicit artifact copy to CPython ast/_ast or source
```

### Python Facade Responsibilities

Python stays deliberately thin:

- normalize public API inputs;
- select one engine before template/state work starts;
- hold opaque native handles on composables, scopes, candidates, and overlays;
- keep Python external objects alive in slot storage owned at the boundary;
- wrap native candidate batches into the existing scope-facing adapter shape;
- render native diagnostic payloads into existing Astichi exceptions;
- call explicit slow-path debug/snapshot/artifact APIs for tests and goldens.

Python must not, on the native success path:

- call `ast.parse(...)` for template extraction;
- build Python `Inventory` or `InventoryRecord` objects for candidate lookup;
- materialize by mutating Python builder state;
- bounce into native once per record, pattern branch, or AST node.

### Native Module Responsibilities

The production native module owns:

- engine lifetime and generation ids;
- canonical surface bundle registration;
- dynamic native handles for surfaces, operations, patterns, templates,
  states, occurrences, records, edges, overlays, and external slots;
- native parser and Astichi AST/IR storage;
- pattern extraction from native parser nodes into template records;
- occurrence and index tables;
- candidate query and compatibility evaluation;
- overlay and resolved-name views;
- materialization-plan and hygiene streams;
- native IR materialization;
- final CPython AST construction at the public artifact boundary;
- deterministic structural snapshots.

## Capability Gates

The extension must advertise concrete features before Python can select it:

```text
native.extension.v1
native.surface_registry.v1
native.pattern_registry.v1
native.parser_ir.v1
native.template_extract.v1
native.template_store.v1
native.occurrence_store.v1
native.record_indexes.v1
native.candidate_query.v1
native.overlay_store.v1
native.materialization_plan.v1
native.hygiene_engine.v1
native.artifact_builder.python_ast.v1
native.full_lower_engine.current_surfaces.v1
```

`auto` may select native only when the extension advertises
`native.full_lower_engine.current_surfaces.v1` and accepts the active surface
bundle, snapshot schema, operation primitives, parser grammar, and artifact
policy. Explicit `native` fails early with a diagnostic if any gate is missing.

The first native roll-build slice should correct any selection behavior that
treats an importable skeleton as a usable native lower engine.

## Native Data Structures

### Engine

```text
Engine {
  epoch: u64
  owner_id: u64
  supported_schema_versions
  surface_registry
  string_interner
  template_store
  external_slots
  parser_backend
}
```

All handles carry owner and generation data so stale or cross-engine handles
fail before doing work.

### Surface Registry

The native registry consumes the same canonical surface bundle as the Python
reference engine. Stable string keys are used at registration time only. Native
hot paths use dynamic ids returned by registration.

```text
SurfaceRegistry {
  bundle_signature
  surfaces_by_key: key -> SurfaceId
  operations_by_key: key -> OperationId
  patterns_by_key: key -> PatternId
  compatibility_rules: Vec<CompiledCompatibilityRule>
  extractor_templates: Vec<CompiledPatternTemplate>
}
```

Pattern templates must be data-driven enough that adding a future syntax
surface does not require a public native API rebuild when it uses an existing
matcher kind and operation primitive.

Supported matcher kinds for the first native implementation:

- direct call marker;
- decorator call marker;
- internal metadata marker;
- payload expression item;
- payload function item;
- definition-name payload;
- identifier suffix;
- sentinel attribute;
- statement prefix;
- loop-unroll marker;
- body/list/clause locator helpers for future surfaces.

New native code is allowed when a truly new matcher kind is invented. New
surfaces that compose existing matcher kinds should be bundle input only.

### Template Store

Native template registration is source-driven:

```text
Template {
  template_id
  template_key
  source_summary
  source_text_ref
  native_module_ir
  locators: Vec<SourceLocator>
  records: Vec<TemplateRecord>
  artifact_metadata
}

TemplateRecord {
  template_record_id
  surface_id
  operation_id
  pattern_id
  resource_name_id
  inventory_kind_id
  code_owner_id
  locator_id
  materialization_role
  compatibility_shape
  flags
}
```

Python-extracted template snapshots may exist as a parity harness input, but
they are not the native success path and must not be used by
`astichi.compile(..., engine="native")`.

### Native AST/IR

The first production path should migrate the probe parser into `native_engine`
instead of reusing CPython AST as the working graph.

Native IR requirements:

- stable node ids for locators and materialization anchors;
- parent/field/index path summaries for snapshots;
- source locations for diagnostics and final artifact construction;
- enough typed structure for expression, statement, argument, parameter,
  clause, import, loop, exception, match/case, and decorator operations;
- mutable materialization copy separate from immutable template IR.

The native IR does not need to mirror CPython `_ast` exactly. It needs a lossless
enough model for Astichi transformations and final artifact copy.

### Assembly State

Record handles are derived from `(OccurrenceId, TemplateRecordId)`. Native does
not need to allocate one full record object per occurrence unless a later
profile proves that faster.

```text
AssemblyState {
  state_id
  occurrence_store
  edge_store
  overlay_store
  record_state_bits
  indexes
  event_order
}

Occurrence {
  occurrence_id
  template_id
  parent_occurrence_id
  build_path_id
  overlay_id
  live
}
```

Indexes required for the current scope API:

- by resource name;
- by inventory kind;
- by `(resource name, inventory kind)`;
- by surface id;
- by code owner;
- by build path;
- by resolved identifier name;
- by unsatisfied demand state.

Indexes may store dense record references and filter dead/satisfied records
with bitsets. Debug inventory projection must be an explicit slow path.

### Candidate Query

Native candidate lookup should be bulk-shaped:

```text
CandidateQuery {
  target_record
  resource_name
  inventory_kind
  target_surface_id
  owner_selector
  resolved_name_selector
  diagnostic_mode
  result_limit
}

CandidateBatch {
  candidates: Vec<Candidate>
  diagnostic_summary
}
```

Candidate acceptance is computed by:

1. choose the smallest relevant index set;
2. filter live records;
3. filter by owner/resolved-name selectors;
4. evaluate compiled compatibility descriptors;
5. return stable candidate keys and record handles in one batch.

The native path must not construct Python `InventoryRecord` objects unless the
caller explicitly asks for a diagnostic projection after lookup.

### Overlay Store

External values cross the boundary by slot handle.

```text
ExternalSlot {
  slot_id
  py_object_ref
  lifetime_owner
}

Overlay {
  overlay_id
  kind
  target_record
  payload
}
```

Overlay kinds:

- composable insertion edge;
- external value binding;
- identifier binding;
- keep-name directive;
- managed import request;
- collision rename/reject decision.

Native owns the resolved-name view used by later candidate queries and hygiene.
Python owns the actual `PyObject` references for external values through safe
PyO3 references.

### Materialization And Hygiene

Materialization and hygiene are native lower-layer responsibilities.

The native planner emits the same structural shape as the Python reference:

```text
MaterializationPlan {
  root_occurrence
  operation_stream
  hygiene_stream
  artifact_requests
  debug_views
}
```

Operations for the current surface set:

- `astichi.operation.append_body`
- `astichi.operation.splice_body_at_marker`
- `astichi.operation.replace_expression`
- `astichi.operation.splice_expression_list`
- `astichi.operation.splice_parameters`
- `astichi.operation.splice_call_arguments`
- `astichi.operation.append_clause`
- `astichi.operation.managed_import_request`
- `astichi.operation.rewrite_identifier`
- `astichi.operation.lower_external_ref`
- `astichi.operation.keep_name`
- `astichi.operation.rename_if_collides`
- `astichi.operation.reject_collision`
- `astichi.operation.strip_marker`
- `astichi.operation.gate_no_unresolved`
- `astichi.operation.unroll_loop`

The planner validates unresolved demand state before artifact construction.
The materializer applies the operation stream to a native materialization copy,
not to Python AST nodes.

### Artifact Builder

Artifact construction is the explicit boundary back to Python:

```text
ArtifactCopyRequest {
  state
  root_occurrence
  artifact_kind: python_ast | source
  location_policy
}
```

The required first artifact is public CPython `ast`/`_ast` node construction.
The builder must populate required/default fields and location metadata without
constructor warnings. Source rendering can remain a verification/debug artifact
until it shows up as a production hot path.

## API Shape

Contract names, not final Python symbol names:

```text
capabilities() -> CapabilitySnapshot
engine_create(request) -> EngineHandle
engine_close(engine) -> None

register_surface_bundle(engine, bundle_snapshot) -> RegisteredBundleSnapshot
register_template_source(engine, source, origin, options) -> TemplateHandle

state_create(engine) -> StateHandle
state_close(state) -> None
append_occurrence(state, template, request) -> OccurrenceHandle

query_candidates(state, request) -> CandidateBatch
apply_candidate(state, request) -> ApplyResult
append_overlays(state, requests) -> OverlayAppendResultBatch

build_materialization_plan(state, request) -> MaterializationPlanSnapshot
copy_artifact(state, request) -> PythonArtifact
structural_snapshot(state, request) -> StructuralSnapshot
debug_inventory_projection(state, request) -> InventoryProjectionSnapshot
```

The API must stay engine-shaped and bulk-shaped. It must not grow one method per
Astichi surface.

## Facade Integration

### Compile

Native-selected `astichi.compile(...)`:

1. selects or creates a native engine;
2. registers the active surface bundle if needed;
3. calls `register_template_source(...)`;
4. returns a `Composable` facade carrying a native template handle;
5. exposes artifact-copy methods for tests and compatibility.

The native path must not call the existing Python marker extraction path.

### AssemblyScope

Native-selected `AssemblyScope`:

1. creates a native state;
2. imports or references native template handles for added composables;
3. appends root/source occurrences through native;
4. routes `find_candidates` to native query;
5. routes `apply` to native edge/overlay APIs;
6. routes external/identifier binding to native overlay APIs;
7. routes materialization to native plan plus artifact copy.

YIDL should continue using the scope API. The facade can preserve YIDL-facing
method names while changing the backing implementation.

## Verification Strategy

Native correctness is proved through shared goldens, not broad duplicated unit
tests.

Required golden gates:

- template structural snapshots for every current `tests/data/gold_src/`
  fixture;
- scope/add/apply structural snapshots for existing lower-engine fixtures;
- materialization-plan structural snapshots;
- final materialized source goldens;
- executable AST smoke tests where the current suite already validates runtime
  behavior;
- YIDL integration/runtime tests that exercise the scope API.

Focused bespoke tests stay narrow:

- stale handle and cross-engine handle diagnostics;
- unsupported capability and grammar diagnostics;
- parser extraction of individual matcher kinds;
- external slot lifetime;
- CPython AST constructor compatibility failures;
- no Python inventory projection on native success path.

Instrumentation gates:

- native compile does not call `ast.parse(...)`;
- native candidate query does not call debug inventory projection;
- native materialization does not mutate Python builder state;
- candidate query uses one bulk native call per logical query;
- artifact copy time is measured separately from native lower work;
- GIL-held time is measured where the backend can expose it.

## Roll-Build Plan

Use tags with the existing `perf-refactor/` prefix. Each slice must pass its
focused tests and the full Astichi suite unless the slice explicitly marks a
native feature as unavailable behind a capability gate.

### N0: Selection And Capability Cleanup

Goal: make selection truthful before native behavior lands.

Work:

- require `native.full_lower_engine.current_surfaces.v1` before selecting
  native for production lower work;
- make explicit `native` fail when only the skeleton is present;
- keep `auto` fallback at engine/template boundaries only;
- add tests for skeleton-present-but-not-capable behavior;
- document capability names in `native_engine/README.md`.

Acceptance:

- an importable skeleton does not route or select native lower behavior;
- explicit native failure is diagnostic;
- full suite passes without building the extension.

### N1: Native Engine Core

Goal: create the native modules and handle/arena foundation.

Work:

- split `native_engine/src/lib.rs` into engine, handles, errors, capabilities,
  and snapshot modules;
- implement engine creation/close;
- implement typed handles with owner, generation, kind, and index;
- implement structured error translation to Python exceptions;
- expose capability snapshots.

Acceptance:

- focused native handle tests pass;
- stale/cross-engine handles fail deterministically;
- no Astichi surface behavior is hardcoded yet.

### N2: Surface Bundle And Pattern Registry

Goal: register the canonical surface bundle natively.

Work:

- consume the Python surface bundle snapshot;
- assign native ids for surfaces, operations, and patterns;
- compile compatibility descriptors;
- lower pattern `template_key` values into matcher-kind descriptors;
- keep dormant future pattern templates registerable but disabled.

Acceptance:

- native and Python registry snapshots match for current and future bundles;
- duplicate/unknown key diagnostics match the Python reference;
- no public API changes are required to add a surface that uses an existing
  matcher kind.

### N3: Native Parser And IR Import From Probe

Goal: move the successful probe parser/artifact core into `native_engine`.

Work:

- add the selected parser dependency to `native_engine`;
- parse source to native module IR;
- store source locations and node ids;
- provide a minimal `copy_python_ast` artifact for unmodified modules;
- benchmark parse and artifact-copy phases separately.

Acceptance:

- current probe fixtures parse and compile through the production extension;
- CPython AST constructor warnings are treated as failures;
- no CPython internal compiler APIs are used.

### N4: Native Pattern Extraction

Goal: extract Astichi template records from native IR.

Work:

- implement matcher kernels for the current pattern kinds;
- produce native template records, locators, materialization roles, and
  compatibility shapes;
- compute deterministic template keys and source summaries;
- emit template structural snapshots.

Acceptance:

- native template snapshots match Python reference snapshots for all current
  gold-source fixtures;
- Python-extracted inventory is used only by the parity harness;
- unsupported syntax produces a template-level diagnostic, not partial native
  state.

### N5: Native Composable Facade

Goal: route compile to native templates behind the public composable facade.

Work:

- add `NativeTemplateBinding` / native-backed composable state;
- route native-selected `astichi.compile(...)` through
  `register_template_source(...)`;
- expose explicit artifact-copy methods used by existing tests;
- keep Python engine as oracle and fallback before native registration only.

Acceptance:

- compile-only structural goldens pass with `ASTICHI_LOWER_ENGINE=native`;
- current public composable methods used by YIDL remain available;
- native compile path has a counter proving no Python `Inventory` extraction.

### N6: Occurrence Store And Indexes

Goal: implement native assembly state for `AssemblyScope.add(...)`.

Work:

- create native state handles;
- append root/source occurrences;
- derive record handles from occurrences and template records;
- maintain required indexes and state bitsets;
- expose structural scope snapshots.

Acceptance:

- add/scope structural snapshots match Python reference;
- append cost is proportional to records in the added template;
- debug inventory projection is not used by scope add.

### N7: Candidate Query

Goal: make native candidate lookup satisfy the scope API.

Work:

- implement candidate query over native indexes;
- evaluate compatibility descriptors natively;
- return candidate batches with stable keys and lazy diagnostics;
- wrap candidate batches in Python facade adapters.

Acceptance:

- candidate goldens and scope lookup fixtures match Python;
- candidate lookup uses no Python inventory projection;
- missing/ambiguous diagnostics stay useful.

### N8: Apply, Edges, And Overlays

Goal: route composition and binding changes into native state.

Work:

- append insertion edges natively;
- mark single-use demands satisfied;
- allocate external slots and store external overlays;
- store identifier overlays and resolved-name views;
- preserve deterministic event order for snapshots.

Acceptance:

- apply/bind overlay snapshots match Python reference;
- YIDL-facing scope operations run against native handles;
- external value lifetime is explicit and tested.

### N9: Native Materialization Plan

Goal: emit native materialization and hygiene streams.

Work:

- build operation streams from native edges, overlays, and unsatisfied records;
- implement hygiene stream decisions for keep-name, rename, import, and
  unresolved-marker gates;
- validate operation ids against the registered bundle;
- snapshot materialization plans.

Acceptance:

- materialization-plan structural goldens match Python reference;
- no per-operation Python callback is needed;
- unresolved state fails before artifact construction.

### N10: Native IR Materializer

Goal: apply materialization operations to a native IR copy.

Work:

- implement expression replacement;
- implement body and defaulted-body splice;
- implement parameter splice;
- implement call-argument splice;
- implement elif/clause append;
- implement managed import placement;
- implement identifier rewrite and collision policy;
- implement external/ref lowering;
- implement marker stripping and loop unroll.

Acceptance:

- final materialized goldens match Python for each enabled surface family;
- native materialization does not construct CPython AST nodes until artifact
  copy is requested;
- every current operation primitive has native execution coverage.

### N11: CPython AST Artifact Builder

Goal: produce executable public CPython AST nodes from materialized native IR.

Work:

- build `_ast`/`ast` module nodes through public constructors or equivalent
  PyO3 calls;
- populate required/default fields for supported Python versions;
- populate or repair source locations according to the selected policy;
- compile returned modules with public `compile(...)`;
- measure artifact copy, source rendering, compile, and exec separately.

Acceptance:

- executable AST tests pass with native artifacts;
- final goldens pass through the same renderer used by the current harness;
- constructor warnings or missing-field warnings fail focused tests.

### N12: Current Surface Closure

Goal: close parity for all currently supported Astichi/YIDL surfaces.

Work:

- run the full Astichi suite with explicit native selection;
- run YIDL integration/runtime tests using the native scope path;
- close any unsupported current surface as a native implementation bug;
- keep future surfaces dormant unless explicitly enabled.

Acceptance:

- all current structural and final goldens pass under native;
- YIDL uses the native lower engine through the scope API;
- Python reference remains available for comparison but is not needed on the
  native success path.

### N13: Performance And Default Selection

Goal: decide default selection after correctness is closed.

Work:

- profile the lifecycle-shaped workload with Python and native engines;
- break down native parse, extraction, candidate query, overlays,
  materialization, artifact copy, source rendering, compile, and exec;
- make `auto` select native by default only when capability and workload gates
  pass;
- document remaining bottlenecks if the hard performance goal is not met.

Acceptance:

- native is a complete selectable engine regardless of the default policy;
- default selection is coarse and deterministic;
- profile output explains any remaining gap to the performance target.

## Stop Conditions

Stop and patch the design before continuing when:

- a current Astichi surface cannot be represented by registered pattern
  templates and operation primitives;
- a native operation would require a new public method per surface;
- candidate lookup needs Python `Inventory` projection on the success path;
- materialization or hygiene needs Python builder-state mutation;
- native parser gaps prevent current supported Python syntax from passing;
- CPython AST artifact construction cannot satisfy public `compile(...)`
  without internal CPython APIs.

## Expected Performance Shape

The largest win should come from removing repeated Python object graph churn,
not from parser speed alone.

Expected improvements after parity:

- template parse/extraction: 2x to 5x on representative templates;
- candidate lookup and inventory merge: 5x to 20x when indexes stay native;
- materialization/hygiene planning: 3x to 10x when operation streams stay
  native;
- end-to-end YIDL lifecycle-shaped workload: likely 1.5x to 4x unless final
  CPython AST/source rendering or downstream runtime dominates.

Those numbers are estimates. The roll-build should measure each phase so the
remaining bottleneck is visible instead of inferred.
