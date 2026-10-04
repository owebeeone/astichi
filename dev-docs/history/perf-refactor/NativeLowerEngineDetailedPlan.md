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

Partial implementation capabilities may be advertised for tests and roll-build
progress, but they must not satisfy the production native selection gate. For
package-v2 work, `native.lower_template_package_v2.snapshot.partial.v1` means
the extension can emit a parity snapshot for a supported subset. Only
`native.lower_template_package_v2.v1` means package rows are complete enough for
native hygiene/materialization planning.

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

### N4a: Template Snapshot Schema And Empty Extraction

Goal: define native template snapshot output and prove extraction for ordinary
sources with no Astichi markers.

Work:

- add native template snapshot request/result shapes;
- compute deterministic template keys and source summaries from native IR;
- emit locators, template records, and diagnostics sections even when empty;
- reject unsupported partial extraction instead of returning mixed state;
- add focused tests for marker-free modules and syntax diagnostics.

Acceptance:

- native marker-free template snapshots are deterministic;
- snapshot shape is ready for record-bearing extraction slices;
- no Python `Inventory` objects are used for native extraction.

### N4b: Direct Call Marker Extraction

Goal: extract direct call marker records from native IR.

Work:

- implement matcher kernels for direct call marker patterns;
- cover `astichi_hole`, `astichi_bind_external`, `astichi_keep`,
  `astichi_export`, `astichi_import`, `astichi_pass`, `astichi_pyimport`,
  `astichi_comment`, and `astichi_ref`;
- produce native template records, locators, materialization roles, and
  compatibility shapes for direct call markers;
- emit template structural snapshots for representative direct-call fixtures.

Acceptance:

- direct call marker snapshots match the Python reference for covered fixtures;
- unsupported direct-call shapes fail before returning partial native state.

### N4c: Identifier Suffix Marker Extraction

Goal: extract identifier suffix marker records from native IR.

Work:

- implement `__astichi_arg__` extraction for names, definition spellings,
  call keyword names, import strings/symbols/aliases, and function parameters;
- implement `__astichi_keep__` extraction for supported spelling positions;
- produce resolved logical names and code-owner summaries compatible with the
  Python reference;
- add parity snapshots for representative identifier fixtures.

Acceptance:

- suffix marker snapshots match the Python reference for covered fixtures;
- extraction records every occurrence needed by candidate lookup and hygiene.

### N4d: Payload Marker Extraction

Goal: extract production records for payload-style markers.

Work:

- implement parameter payload extraction from `astichi_params`;
- implement function-call argument payload extraction from `astichi_funcargs`;
- implement expression and block production extraction;
- cover payload-local boundary directives where they affect template records;
- add parity snapshots for representative payload fixtures.

Acceptance:

- payload snapshots match the Python reference for covered fixtures;
- payload extraction preserves enough locator data for later materialization.

### N4e: Decorator And Internal Metadata Extraction

Goal: extract internal insert metadata and decorator-carried records.

Work:

- implement `@astichi_insert(...)` decorator extraction;
- implement expression-form `astichi_insert(...)` metadata extraction;
- preserve `ref`, `kind`, `order`, and pyimport metadata required by later
  materialization;
- add parity snapshots for staged build and emitted-source fixtures.

Acceptance:

- internal metadata snapshots match the Python reference for covered fixtures;
- malformed metadata fails with native diagnostics before partial state.

### N4f: Special Surface Extraction

Goal: extract the remaining current special surfaces.

Work:

- implement defaulted block-hole extraction;
- implement elif target and elif production extraction;
- implement compile-time unroll marker extraction;
- implement pyimport top-of-scope prefix validation metadata;
- add parity snapshots for representative special-surface fixtures.

Acceptance:

- special-surface snapshots match the Python reference for covered fixtures;
- dormant future patterns remain registered but disabled.

### N4g: Current Gold-Source Extraction Closure

Goal: close native pattern extraction for all current gold-source fixtures.

Work:

- replace the old AST-only `_=astichi_import/export(...)` funcargs directive
  carrier with the parseable reserved keyword carrier
  `__astichi_ph_{N}__=astichi_import/export(...)`, and reject `_=` inside
  `astichi_funcargs(...)`;
- run native extraction against every `tests/data/gold_src/*.py` fixture;
- compare native template snapshots against the Python reference;
- add/update structural goldens only where the new native snapshot grammar
  requires it;
- keep Python-extracted inventory only as the parity oracle.

Acceptance:

- native template snapshots match Python reference snapshots for all current
  gold-source fixtures;
- unsupported current syntax is treated as a native implementation bug;
- the next slice can route a native composable facade on top of extracted
  native template records.

### N5a: Native Template Snapshot Overlay

Status: landed as the first N5 checkpoint.

Goal: prove explicit native compile can attach native-extracted structural
template snapshots without changing the public composable API.

Work:

- route explicit native-selected `astichi.compile(...)` through native
  extraction;
- attach the native structural snapshot to the facade binding;
- keep Python `record_specs` available for the current Python scope path;
- keep `auto` on Python because this is not a complete lower engine.

Acceptance:

- compile-only structural snapshots match the Python reference;
- current public composable methods used by YIDL remain available;
- native full-lower-engine capability is not advertised.

### N5b: Native Template Binding And Scope Cache

Goal: make native template registration an explicit scope-owned cache rather
than a temporary extraction handle.

Work:

- add a native template binding shape that carries the native snapshot/source
  data needed to register into a scope-owned native engine;
- add a native template cache parallel to `LowerTemplateCache`;
- register template snapshots into the scope native engine and retain template
  handles there;
- keep Python `record_specs` only as the oracle/adapter path until candidate
  query is native.

Acceptance:

- a native-selected composable can be registered into a native scope engine
  without reparsing Python AST or rebuilding `Inventory`;
- repeated adds of the same composable reuse the native template handle;
- cross-engine template handles reject deterministically.

### N6a: Native Occurrence Store And Index Primitives

Status: landed as the first N6 checkpoint.

Goal: implement the lower native data structure primitives needed by
`AssemblyScope.add(...)`.

Work:

- create native state handles;
- append root/source occurrences;
- derive record handles from occurrences and template records;
- maintain required indexes and state bitsets;
- expose structural scope snapshots.

Acceptance:

- low-level native add/state snapshots match Python reference fixtures;
- append cost is proportional to records in the added template;
- record and occurrence handles reject stale/cross-engine use.

### N6b: Native Scope Add Route

Goal: make `AssemblyScope.add(...)` append into native state through native
handles while the Python path still runs as the parity oracle.

Work:

- initialize a scope-owned native engine/state when native is explicitly
  selected;
- dual-write root and child occurrence appends to native and Python lower state
  during the transition;
- expose native structural snapshots for add-only scopes;
- add counters proving the native append path does not use debug inventory
  projection.

Acceptance:

- add-only structural goldens match through the native scope snapshot;
- Python lower state can still be compared in tests, but native append does
  not depend on Python `Inventory`;
- `native.full_lower_engine.current_surfaces.v1` remains disabled.

### N7a: Native Candidate Query For Composable Inserts

Goal: satisfy additive composable lookup from native indexes for the current
hole/production families.

Work:

- implement native record lookup by name, build path, owner path, surface, and
  inventory kind;
- evaluate compatibility descriptors natively for expression, block,
  parameter, call-argument, and elif surfaces;
- return stable candidate payloads containing native target records and
  compatible production records;
- wrap native candidate batches in Python facade adapters without projecting a
  Python `Inventory`.

Acceptance:

- composable candidate goldens and scope lookup fixtures match Python;
- candidate lookup uses native indexes and compatibility rules only;
- missing and ambiguous candidate diagnostics stay stable.

### N7b: Native Candidate Query For External And Identifier Demands

Goal: satisfy the non-composable scope API lookups from native indexes.

Work:

- implement native external demand lookup;
- implement native identifier demand lookup;
- apply overlay-resolved owner-name views when filtering by owner path;
- return stable diagnostics for missing and ambiguous external/identifier
  candidates.

Acceptance:

- external-value and identifier candidate fixtures match Python;
- owner selector behavior matches after identifier overlays;
- no Python inventory projection is required for lookup.

### N8a: Native Composable Apply

Goal: route composable insertion application into native edges and state bits.

Work:

- append insertion edges natively;
- mark single-use additive demands satisfied natively;
- attach child occurrences under their parent occurrence handles;
- preserve deterministic edge/order snapshots.

Acceptance:

- composable apply structural snapshots match Python reference;
- staged build fixtures can apply composable candidates through native handles;
- Python builder mutations remain an adapter fallback only.

### N8b: Native External Slots And External Overlays

Goal: store external-value binding state in the native lower layer.

Work:

- allocate explicit external slot handles;
- keep Python external object references alive at the facade boundary;
- store native external overlays and mark demands satisfied;
- expose enough artifact metadata for later external/ref lowering.

Acceptance:

- external bind overlay snapshots match Python reference;
- external object lifetime is explicit and tested;
- external lookup/apply does not mutate Python builder state on the native path.

### N8c: Native Identifier Overlays And Resolved Owner Views

Goal: make identifier binding and owner-path resolution native-owned.

Work:

- store identifier overlays natively;
- maintain resolved-name views for later owner selectors;
- update code-owner lookups without rewriting template records;
- keep overlay event order deterministic.

Acceptance:

- identifier overlay snapshots match Python reference;
- later owner selectors observe resolved names;
- identifier apply does not require Python inventory projection.

### N9a: Native Materialization Operation Stream

Goal: generate native materialization operations for applied insertion edges.

Work:

- build operation streams from native edges and target records;
- validate operation ids against the registered bundle;
- include source occurrence, target record, order, and operation captures;
- snapshot operation streams for expression, block, parameter, call-argument,
  and elif targets.

Acceptance:

- operation-stream structural goldens match Python reference for insertion
  edges;
- no per-operation Python callback is needed;
- unsupported operation ids fail before artifact construction.

### N9b1: Native Overlay And Unresolved Gate Streams

Goal: generate native overlay operations and the unresolved-state gate from
native lower state.

Work:

- emit external/ref lowering operations from native overlays;
- emit unresolved-marker diagnostics from native state.

Acceptance:

- materialization-plan structural goldens match Python reference for insertion
  plus overlay cases that do not need marker-local hygiene;
- unresolved native state fails before artifact construction;
- overlay stream construction does not need Python builder-state mutation.

### N9b2: Lower Template Package V2 Contract

Status: Python contract landed through the package-only materialization-plan
guard. Native has a package-v2 snapshot entry point for the first subset, but
does not yet advertise `native.lower_template_package_v2.v1`.

Goal: promote marker, scope, managed-import, and local-binding facts into the
shared lower-engine contract before native hygiene implementation.

This is a design/API slice, not a native-private metadata patch. The Python
system already has these facts on `BasicComposable.markers`, name
classification, and source AST walks. The lower engine does not yet own or
expose them. Native cannot complete hygiene/materialization ownership until the
same behavior-affecting data is available through a canonical lower-template
package.

Work:

- add `LowerTemplatePackageV2` as the canonical records, locators, scopes,
  markers, and managed-import contract;
- encode package runtime rows with interned strings, path tables, typed arrays,
  and flags rather than nested debug dictionaries;
- add package snapshot goldens that expose behavior-affecting data but keep
  derived indexes out of the contract;
- refactor Python materialization planning so hygiene decisions read from
  package/state APIs rather than `BasicComposable` side channels.

Acceptance:

- Python package projections contain the marker, scope, local-binding, and
  managed-import facts needed by current hygiene goldens;
- Python materialization-plan goldens still pass after side-channel removal;
- native package extraction has a concrete parity target for N9b3.

Implementation detail:

- the Python-first roll-build slices are specified in
  `dev-docs/perf-refactor/PythonLowerTemplatePackageV2Plan.md`;
- the Python plan is complete through the package-only plan-construction guard;
- native N9b3 resumes from the package-v2 snapshot grammar rather than from
  structural template snapshots alone.

Native parallel work:

- N9a operation streams and N9b1 overlay/gate streams are package-independent
  and may be completed before P5d;
- native work that only consumes records, locators, edges, overlays, or final
  artifact-copy primitives may proceed before P5d;
- native marker/scope/managed-import extraction must wait for the v2 package
  schema to stabilize, except for throwaway spike code.
- production native selection remains disabled until the native backend
  advertises both `native.full_lower_engine.current_surfaces.v1` and
  `native.lower_template_package_v2.v1`; package-v2 rows are now the
  materialization/hygiene contract.

### N9b3a: Native Package V2 Builder And Snapshot API

Status: introduced for records, scopes, generic marker rows, pyimport rows,
managed-import rows, and comment rows. Ref and unroll typed rows are deliberately
left to the following splits.

Goal: give native a first-class package-v2 output surface that can be compared
directly with the Python oracle.

Work:

- implement native package-v2 row storage and deterministic snapshot writing;
- extract template records/locators into package rows from the native parser
  path;
- extract lexical scopes, local bindings, argument bindings, generic marker
  rows, `astichi_pyimport` typed rows, managed-import rows, and
  `astichi_comment` typed rows;
- advertise only
  `native.lower_template_package_v2.snapshot.partial.v1`, not the complete
  package-v2 capability.

Acceptance:

- native package snapshots match the Python package-v2 oracle for expression
  holes, binding/scope rows, boundary markers, managed imports, and comments;
- complete native selection remains blocked because
  `native.lower_template_package_v2.v1` is not advertised;
- no Python `Inventory` object is used to construct the native package snapshot.

### N9b3b: Native Ref And Unroll Package Rows

Status: implemented for native package snapshots. The production package-v2
capability remains disabled until package rows are stored on native template
handles and package-derived hygiene streams land.

Goal: finish the typed package rows that are needed by current materialization
and future surface extension.

Work:

- extract `astichi_ref` value and sentinel-attribute typed rows, including
  context and literal path;
- extract `astichi_for` statement-context typed rows, including target, domain,
  body, orelse, target binding set, domain shape, and flags;
- keep generic marker source ordering identical to the Python oracle.

Acceptance:

- native package snapshots match Python package-v2 goldens for ref and unroll
  fixtures;
- marker ids line up between generic rows and typed ref/unroll rows;
- unsupported ref/unroll shapes fail before returning partial package state.

### N9b3c: Native Package Rows In Template Store

Status: implemented for source-backed native template registration. Structural
snapshot registration remains a parity/import harness and intentionally does
not synthesize stored package rows.

Goal: stop treating package-v2 snapshots as a standalone diagnostic and store
package rows with native templates.

Work:

- attach package-v2 row storage to native template handles;
- register source-backed templates with native IR, structural records, and
  package rows in one native template store;
- keep `register_template_snapshot` as a parity/import harness only;
- expose template package snapshots from stored template handles.

Acceptance:

- scope-owned native template registration does not need a Python structural
  snapshot on the success path;
- native template handles carry both structural records and package rows;
- package snapshots remain deterministic after template-cache reuse.

### N9b3d: Native Package-Derived Hygiene Streams

Status: implemented for package-owned gate captures, marker hygiene,
managed-import requests, pyimport collision renames, and block-boundary
collision renames. Native now advertises `native.lower_template_package_v2.v1`;
the full lower-engine capability remains disabled.

Goal: make marker-local hygiene and managed import planning native-owned using
the v2 lower-template package.

Work:

- build native package-derived indexes for marker lookup, scope binding lookup,
  and managed import lookup;
- emit keep-name, strip-marker, managed-import, and rename-if-collides hygiene
  operations natively;
- preserve the same deterministic hygiene ordering as the Python oracle.

Acceptance:

- materialization-plan structural goldens match Python reference for managed
  import, boundary marker, keep collision, and boundary-elif cases;
- hygiene/materialization planning no longer needs Python builder-state
  mutation;
- native capabilities include `native.lower_template_package_v2.v1`, allowing
  explicit native lower-engine selection to pass the package-v2 gate once the
  rest of the native lower-engine gate is also closed.

### N10a: Native IR Clone And Locator Mutation Primitives

Goal: establish safe native mutation primitives before implementing each
surface family.

Work:

- clone native template IR into a materialization workspace;
- resolve stored locators to mutable native IR nodes/lists;
- implement splice/replace helper primitives with path diagnostics;
- add round-trip tests for unchanged modules and locator failures.

Acceptance:

- mutation helpers never construct CPython AST nodes;
- bad locators fail with useful diagnostics;
- unchanged native IR can still be copied to artifacts later.

Status: implemented for source-backed template IR cloning, locator resolution
diagnostics, root/module locator resolution, and a statement replacement
primitive over cloned native IR.

### N10b1: Native Expression Materializer

Goal: materialize expression replacement over native IR.

Work:

- implement expression replacement for expression holes;
- strip consumed expression markers.

Acceptance:

- expression materialized snapshots match Python reference for the supported
  subset;
- native expression replacement operates on source-backed native template IR;
- no Python AST mutation is used on the native path.

Status: implemented for applying a native `replace_expression` edge to a cloned
native materialization workspace. The copied source expression remains native IR
until the explicit artifact boundary.

### N10b2a: Native Literal Ref Materializer

Goal: materialize literal `astichi_ref(...)` marker forms over native IR.

Work:

- lower literal `astichi_ref("pkg.path")` value forms to native
  `Name`/`Attribute` chains;
- lower literal sentinel forms such as `astichi_ref("self.field")._` and
  `.astichi_v` while preserving store/delete context;
- leave f-string, external-bound, and method-form refs for the external/ref
  overlay slice unless native can reduce them without facade-owned values.

Acceptance:

- literal ref materialized snapshots match Python reference;
- no Python AST mutation is used on the native path.

Status: implemented for literal value-form refs and literal sentinel refs over
cloned native IR. External-bound and dynamic refs remain in N10b2b.

### N10b2b: Native External/Dynamic Ref Overlay Materializer

Goal: materialize external overlays and dynamic `astichi_ref(...)` forms over
native IR while keeping Python object ownership at the facade boundary.

Work:

- lower external slots into artifact placeholders or copied values according
  to the existing facade policy;
- lower f-string, external-bound, and method-form `astichi_ref(...)` values
  after overlay values are available;
- strip consumed external/ref markers;
- keep external Python object ownership in the Python facade while native owns
  the marker rewrite decisions.

Acceptance:

- external/dynamic-ref materialized snapshots match Python reference;
- executable subset tests pass once copied through the artifact boundary;
- no Python AST mutation is used on the native path.

Status: implemented for a first external-overlay literal primitive: native
workspaces can consume an external overlay handle plus a literal expression
payload, replace matching `astichi_bind_external(name)` uses in native IR, and
then lower the now-literal ref. Remaining work is scope-shadow complete
substitution and arbitrary Python object slots at the artifact boundary.

### N10c1: Native Block Splice Materializer

Goal: materialize statement-body insertions over native IR.

Work:

- implement body splice for `splice_body_at_marker` edges;
- preserve statement ordering and source-location policy.

Acceptance:

- block insertion snapshots match Python reference for the supported subset;
- marker stripping is native-owned.

Status: implemented for single native block splice edges over cloned native IR.
Defaulted block fallback and boundary hygiene remain in N10c2.

### N10c2: Native Defaulted Block And Boundary Hygiene Materializer

Goal: finish defaulted statement-body insertions and boundary-marker effects.

Work:

- implement defaulted-body fallback selection;
- strip boundary and keep markers after applying operations;
- apply keep-name and scoped rename hygiene for block insertions;
- preserve statement ordering and source-location policy.

Acceptance:

- defaulted-block/boundary-hygiene goldens match Python reference;
- unresolved block demands fail before artifact copy;
- marker stripping is native-owned.

### N10d1: Native Parameter And Positional Call-Argument Materializer

Goal: materialize the first parameter and call-argument payload surfaces.

Work:

- implement simple positional parameter splice;
- implement positional `*astichi_hole(...)` call-argument splice;
- preserve source ordering for payload items.

Acceptance:

- simple parameter and positional call-argument materialized snapshots match
  Python reference;
- no legacy `_=` carrier is accepted.

Status: implemented for positional parameter payloads and positional
`astichi_funcargs(...)` payloads over cloned native IR. Varargs, kwargs,
defaults, duplicate diagnostics, and payload-local import/export remain in
N10d2.

### N10d2: Native Complete Parameter And Call-Argument Materializer

Goal: finish function parameter and call-argument payload surfaces.

Work:

- implement vararg/kwarg/default ordering checks;
- implement call-argument payload lowering for plain, `*`, and `**` regions;
- enforce duplicate keyword and positional/keyword compatibility diagnostics;
- preserve payload-local import/export semantics.

Acceptance:

- full parameter and call-argument goldens match Python reference;
- payload diagnostics match the Python oracle;
- no legacy `_=` carrier is accepted.

### N10e1: Native Identifier Rewrite Materializer

Goal: apply identifier overlays over native IR.

Work:

- rewrite identifier suffix surfaces such as `name__astichi_arg__`;
- rewrite matching native `Name`/argument/function/class identifiers;
- preserve the source-label ownership model from native overlays.

Acceptance:

- identifier-overlay materialized snapshots match Python reference for the
  supported subset;
- Python lower state is not read during the native rewrite.

Status: implemented for identifier overlays over cloned native IR, including
class/function names, argument names, and expression names.

### N10e2: Native Elif, Pyimport, Identifier Completion, And Unroll Materializer

Goal: close the remaining current materialization surfaces in native IR.

Work:

- implement elif/clause append materialization;
- implement managed import placement after module docstring/future imports;
- finish identifier rewrite cases not covered by N10e1;
- implement compile-time unroll using native IR;
- run surface-family focused goldens before broad closure.

Acceptance:

- elif, pyimport, identifier, and unroll goldens match Python reference;
- future dormant surfaces remain disabled;
- every current operation primitive has native execution coverage.

### N11a: CPython AST Artifact Builder Baseline

Goal: copy native IR to public CPython `ast`/`_ast` nodes for a narrow
executable subset.

Work:

- build module, statement, expression, argument, and context nodes through
  public constructors or equivalent PyO3 calls;
- populate required/default fields for supported Python versions;
- compile returned modules with public `compile(...)`;
- treat constructor warnings or missing-field warnings as failures.

Acceptance:

- marker-free and expression-subset executable AST tests pass;
- artifact copy, source rendering, compile, and exec are timed separately;
- no internal CPython compiler APIs are used.

Status: implemented for materialization workspaces using the public CPython
AST constructors already proven by the native parser probe. Workspace artifact
copy defaults to `fix_missing` locations until source text is carried with the
workspace.

### N11b: CPython AST Artifact Builder Current Surface Coverage

Goal: copy every current materialized native surface to executable public
CPython AST nodes.

Work:

- cover class/function heads, decorators, imports, parameters, calls, elif,
  unroll output, and managed hygiene rewrites;
- repair or preserve source locations according to the selected policy;
- render final goldens through the existing harness;
- add version-specific coverage where CPython constructor requirements differ.

Acceptance:

- executable AST tests pass with native artifacts for current surfaces;
- final goldens pass through the same renderer used by the current harness;
- artifact construction remains an explicit boundary, not a materialization
  dependency.

### N12a: Scope API Native Route

Goal: route the existing Python-facing scope API through native lower-engine
handles once native package, hygiene, materialization, and artifact copy are
complete.

Work:

- make `astichi.compile(...)` attach native package/template handles without
  requiring Python `LowerEngine` registration on the native success path;
- make `AssemblyScope` candidate lookup, edge application, overlay binding,
  materialization, and artifact copy use native state as the authoritative
  state when explicit native selection is active;
- keep Python package/lower-engine snapshots available as oracle diagnostics
  and fallback-only artifacts, not as required success-path inputs;
- run YIDL lifecycle generation with explicit native selection through the
  existing `astichi.compile` and `astichi.build` surfaces.

Acceptance:

- YIDL generation succeeds with `ASTICHI_LOWER_ENGINE=native` through the scope
  API and produces the same generated source as the Python lower engine;
- explicit native scope builds do not mutate Python lower state after template
  registration;
- native route diagnostics identify the first missing native surface or artifact
  boundary instead of silently falling back to Python;
- Python reference routing still works unchanged.

### N12b: Current Surface Closure And Native Capability Gate

Goal: close parity for all currently supported Astichi/YIDL surfaces and only
then advertise the full native lower-engine capability.

Work:

- run the full Astichi suite with explicit native selection;
- run YIDL integration/runtime tests using the native scope path;
- close any unsupported current surface as a native implementation bug;
- remove Python lower-state dependency from the native success path;
- keep future surfaces dormant unless explicitly enabled;
- advertise `native.full_lower_engine.current_surfaces.v1` only after the
  native success path is complete.

Acceptance:

- all current structural and final goldens pass under native;
- YIDL uses the native lower engine through the scope API;
- Python reference remains available for comparison but is not needed on the
  native success path;
- explicit native selection fails if any required capability gate is missing.

### N12c: Final Integration Verification

Goal: prove the complete native route through the real Astichi and YIDL entry
points before treating the capability gate as product-ready.

Work:

- run native-selected `astichi.compile`, `astichi.build`, and scope API calls
  through the same facade surfaces used by YIDL;
- run YIDL lifecycle generation and the lifecycle-shaped runtime workload with
  native selected explicitly and with `auto`;
- verify that final generated source, executable artifacts, diagnostics, and
  golden snapshots match the Python lower engine;
- verify that the native route does not read or mutate Python lower-engine
  inventory/package state after native template registration;
- document any intentionally remaining Python facade responsibilities.

Acceptance:

- explicit native selection succeeds for YIDL lifecycle generation without
  Python lower-state fallback;
- `auto` selects native only when the full native capability gate is present;
- generated YIDL source and runtime behavior match the Python reference;
- remaining Python-owned behavior is boundary/facade work, not lower-engine hot
  path work.

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
