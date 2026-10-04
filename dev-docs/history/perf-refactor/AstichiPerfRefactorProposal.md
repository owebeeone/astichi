# Astichi Performance Refactor Proposal: Inventory-First Assembly

Status: proposal.

This proposal defines a new Astichi assembly architecture for performance work
exposed by the YIDL lifecycle import path. It assumes the current Astichi
semantics are substantially correct and should remain the validation contract.
The goal is not to replace the public model with a vague direct class-builder
shortcut. The goal is to keep the working source/marker model, but move hot
assembly work out of Python AST mutation and Python `Inventory` object churn.

Detailed implementation design and sliced rollout documents live under
`dev-docs/perf-refactor/`. Those documents expand this proposal into data
structure, operation, verification, and build-slice plans.

The proposed architecture has two layers:

1. a Python-facing Astichi facade that preserves the YIDL integration surface
   and the test surfaces needed to validate behavior;
2. a lower assembly library that owns inventory merge, matching, occurrence
   state, and assembly indexing.

The lower library is initially implemented in Python so the existing test suite
and goldens can validate behavior incrementally. The same boundary is designed
so a later native implementation can perform the hard work without changing the
Python facade or Astichi semantics. Native may mean Rust, C++, or a hybrid
module; C++ is not a requirement.

## Problem Statement

Current YIDL lifecycle import profiling shows the runtime decorator path is
dominated by general Astichi assembly and materialization, not by Python
`compile()` or `exec()`.

The representative workload is:

```bash
python -c 'import pyrolyze.runtime.context_lcm'
```

with source roots on `PYTHONPATH`. The measured split in
`dev-docs/AstichiPerfAnal.md` is:

| Phase | 8 classes | Per class |
| --- | ---: | ---: |
| Harvest lifecycle facts | 0.002 s | 0.0003 s |
| YIDL/Astichi assembly | 4.597 s | 0.575 s |
| Materialize to executable AST | 0.660 s | 0.083 s |
| Compile and exec AST | 0.009 s | 0.001 s |
| Call `build_lifecycle_class` | 0.000 s | 0.000 s |
| Total decorator work | 5.268 s | 0.659 s |

The current model does many correct operations at the wrong granularity:

- select one contribution;
- mutate the builder graph;
- apply one binding;
- clone or rebuild a composable;
- rediscover markers, scopes, ports, and inventory;
- refresh or freeze inventory;
- repeat.

This turns assembly into a per-edge compiler pipeline. The new model should
make assembly a table/index problem over inventory records, then build final AST
only once.

## Relationship To Existing Performance Plans

This proposal is the strategic replacement for the current graph-mutation hot
path. It does not invalidate the measurements or near-term hypotheses in
`dev-docs/AstichiPerfAnal.md`, and it should be read alongside that document.

`dev-docs/AstichiPerformanceFixDetailedPlan.md` describes tactical fixes to the
current model: incremental inventory, copy reduction, batched merge, delayed
materialization, and generated-AST cache work. Those fixes are compatible with the
direction here, but they can duplicate effort if they land independently.

Recommended policy:

- use this proposal as the primary direction for the YIDL/Astichi assembly hot
  path;
- ship tactical H1/H2 work only when it is small, low-risk, and not throwaway;
- keep cache and pre-generated-module work as a parallel track for the strict
  import-time budget;
- gate native work on the Python lower-engine prototype proving the boundary.

Native work should also consider a separate parser/emitter path: parse source
text with a native parser, transform a native AST or normalized Astichi AST IR
below the Python object boundary, and instantiate CPython `ast`/`_ast` nodes
only for the final materialized artifact.

The default final artifact boundary should use public CPython `ast`/`_ast`
construction and public `compile(...)`. Internal CPython compiler APIs such as
`PyArena` or `_PyAST_Compile` are version-sensitive and should require a
separate spike before they become a backend dependency.

The immediate proof point is the `AssemblyScope` path. If the lower-engine
prototype does not remove per-apply composable rebuild and inventory projection
from candidate lookup, fall back to the tactical plan before widening the
refactor.

## Compatibility Policy

This performance refactor may make breaking Astichi API changes. The required
compatibility target is the API surface used by YIDL, especially the runtime
assembly path. Broader public Astichi APIs are allowed to move when that makes
the lower-engine boundary cleaner, provided YIDL is updated and the behavior
contract is still validated by tests and goldens.

Review of the current YIDL source shows three relevant surfaces.

### Required Hot Surface

`yidl/generation/assembly_runtime.py` is the import-time hot path for generated
YIDL assemblies. It uses:

- `astichi.build()`;
- `AssemblyScope(astichi.build())`;
- `scope.add(name, composable)`;
- `scope.inventory` as the current candidate lookup argument;
- `find_candidates(...)`;
- `require_one(...)`;
- `scope.apply(candidate)`;
- `scope.build(unroll=...)`;
- `as_composable(...)`;
- `as_external_value(...)`;
- `as_identifier(...)`;
- `BindingCandidate.demand_record` for same-site binding collapse;
- resource `instance_name` for concrete build path tracking.

This is the surface the lower engine must support first. It is acceptable to
change this surface if YIDL changes with it. In fact, replacing
`find_candidates(scope.inventory, ...)` with a direct lower-engine query is
expected because projected Python inventory must not remain on the hot path.

### Required Generated Lifecycle Boundary

`yidl-lifecycle/src/yidl_lifecycle/lifecycle.py` depends on generated assembly
returning a composable that supports:

- `to_executable_ast()` for runtime decoration;
- `emit_commented()` for generated source/debug surfaces.

The lifecycle harvester and container builder are not the bottleneck; the
assembly result boundary is.

### Adaptable Generator Surfaces

Other YIDL generation modules use broader Astichi facilities:

- `astichi.compile(...)` with `file_name`, `line_number`, `offset`,
  `arg_names`, `keep_names`, and `source_kind`;
- fluent `astichi.build()` APIs such as `builder.add.Root(...)`,
  indexed families, `builder.instance(...).target(...)`, and
  `target.add(..., arg_names=..., bind=..., keep_names=...)`;
- composable methods such as `bind`, `bind_identifier`, `with_keep_names`,
  `materialize`, `emit`, `describe`, and direct compiled-AST execution in a few
  non-hot generator paths.

These surfaces are useful validation coverage, but they are not all mandatory
API contracts for the performance refactor. If preserving one of them forces
the lower engine into a weak design, prefer changing the YIDL caller and
updating the relevant tests.

## Authority And Handoff

This document is design rationale, not a second source of implemented truth.
When a phase becomes current behavior, update
`dev-docs/AstichiSingleSourceSummary.md`, relevant reference docs, and tests.

Until then, `dev-docs/AstichiSingleSourceSummary.md` and
`dev-docs/AstichiCodingRules.md` remain the active Astichi handoff and coding
rules.

## Migration Guardrails

The current review disposition is:

- prune unused assembly APIs before other code modifications;
- define the structural verification format before relying on new intermediate
  snapshots;
- approve Phase 0 counters;
- approve a narrow Phase 1 Python lower-engine prototype;
- do not start broad Phase 2 route-through until the authoritative-state
  invariant, materialization coverage, validation timing, and bridge/projection
  counters in this document are treated as phase gates;
- allow breaking Astichi API changes outside the YIDL integration surface when
  they simplify the lower-engine boundary;
- make "no per-apply composable rebuild in `AssemblyScope.apply(...)`" a Phase 2
  hard gate, not a later optimization;
- delay native work until the Python lower engine proves both behavior and a
  remaining measured bottleneck.

These guardrails should prevent the migration from becoming a dual-state bridge
that appears fast only because cost moved from `scope.apply(...)` into
`scope.build()`, inventory projection, or a legacy-builder translation layer.

## Core Thesis

The AST should not be the assembly substrate.

The AST is an immutable source template payload. It provides:

- Python nodes to replicate during materialization;
- marker locations;
- hole and production shapes;
- scope boundaries;
- provenance and ref-path locators.

The inventory is the assembly substrate. It provides:

- currently visible demands and supplies;
- build-path occurrences;
- owner and scope relationships;
- target lookup;
- binding lookup;
- satisfaction state;
- edge and resource attachment records;
- deterministic debug projection.

Hot assembly should mutate or copy-on-write inventory/index state, not clone AST
trees or rebuild Python-facing `Inventory` objects after every operation.

## Prototype Defaults

The first prototype should resolve several design choices up front so the work
does not stall on open-ended infrastructure questions.

### Record Ids

Occurrence-remapped records should use a stable composite identity:

```text
record_id = (occurrence_id, template_record_id)
```

The Python reference implementation can store this as a small tuple or compact
value object. A native engine may bit-pack it internally, for example into a
64-bit integer, if the limits are acceptable. The semantic contract is the
composite identity, not the physical encoding.

Projection to Python `InventoryRecord` should render current-style record ids
for diagnostics and tests. The lower engine should not allocate diagnostic
strings during normal assembly.

### Build Paths

Build paths should be represented inside the lower engine by opaque
`build_path_id` handles produced by a path interner.

The proposal intentionally does not require a specific physical layout for
build paths. Full path bit-packing is risky as an up-front contract because
paths are variable-length, include interned string/indexed segments, and need
prefix queries and debug rendering. The implementation can still use packed
segments, trie nodes, or packed short-path fast lanes behind `build_path_id`.

The first Python engine should use the simplest path interner that preserves
current tuple-path semantics. A native engine should choose trie or packed
storage after Phase 2 profiles show whether path lookup is material.

### Semantic Kinds

Lower records may use compact `kind_id` values, but those ids are interned
references to existing Astichi semantic objects or metadata derived from them.
They are not a new public category API.

The Python reference engine should delegate compatibility decisions to existing
descriptor and port semantics where practical. A native engine can later mirror
those decisions with generated semantic tables, but the Python projection must
continue to rehydrate current semantic objects.

Any native semantic table must be generated from a single owned semantic schema
or from the Python semantic objects. Serialized or generated tables should carry
a semantic version and content signature so stale cached data cannot silently run
against newer Python semantics. In-process native execution should bind specs by
registration: native code returns handles for registered
patterns/surfaces/operations, and later calls use those handles. The Python
reference engine remains behavior-first; the native implementation must prove
parity for each mirrored decision.

### Target Metadata

Template registration should precompute target-site metadata:

```text
target name -> target record ids
target ref path -> shell/scope locator
hole names
elif target names
parameter hole names
```

This moves `_validate_registered_target_site`-style repeated scans out of the
hot path. Target validation remains part of assembly, but it should query
template indexes instead of rescanning Python AST bodies.

## Layer 1: Python-Facing Facade

The Python-facing layer preserves the YIDL-facing shape and enough test-facing
shape to validate behavior. It does not need to preserve every current Astichi
public API if doing so weakens the lower-engine design.

Responsibilities:

- keep or adapt the YIDL-used `AssemblyScope`, builder, composable, descriptor,
  and inventory surfaces;
- translate source templates into lower-library template descriptors;
- call the lower assembly library for scope operations;
- expose Python `Inventory` and descriptor objects as a debug/public projection;
- keep existing tests and goldens as the primary behavior validation layer,
  updating API-facing tests when the intentionally supported surface changes;
- adapt lower-engine materialized artifacts to Python-facing return types, such
  as `BasicComposable`, executable AST, emitted source, and debug snapshots.

The facade should remain intentionally thin on the hot path. Its job is to
normalize user inputs, preserve diagnostics, and delegate assembly,
materialization, and hygiene work to the lower engine.

The important compatibility point is `AssemblyScope`. The existing scope API is
already the assembly boundary used by YIDL runtime helpers. The refactor should
optimize for this API first:

```python
scope = AssemblyScope(astichi.build())
scope.add("Root", root_composable)
candidate = require_one(find_candidates(scope.inventory, resource, ...))
scope.apply(candidate)
result = scope.build()
```

The facade may continue to expose `scope.inventory` as a Python object, but that
object must become a snapshot/projection. Normal candidate lookup and apply
paths should use lower-engine handles and indexes directly.

`find_candidates(...)` is therefore part of the migration, not an afterthought.
If the YIDL runtime still calls `find_candidates(scope.inventory, ...)` and that
call materializes a Python `Inventory`, the main win is lost. The facade should
route candidate lookup through lower-engine indexes whenever the inventory value
is backed by an active lower-engine assembly.

## Layer 2: Lower Assembly Library

The lower library is the terminal assembly engine. It owns the performance
critical model.

Initial implementation:

- Python, in-tree, behaviorally equivalent to current Astichi;
- explicit API boundary;
- no dependency on Python AST mutation for hot assembly;
- lower-owned materialization and hygiene, implemented in Python first;
- structural verification snapshots for intermediate state;
- benchmarked and validated against existing tests.

Target implementation:

- alternate native engine behind the same API;
- owns inventory merge, indexing, matching, occurrence overlays,
  materialization, and hygiene;
- returns opaque handles, compact debug snapshots, materialized artifacts, and
  verification snapshots to Python.

The lower library should traffic primarily in ids, not Python objects:

```text
template_id
occurrence_id
record_id
scope_id
owner_id
target_id
semantic_kind_id
string_id
```

Python-facing objects are projections over these ids. They are not the
authoritative assembly state.

The lower engine also owns the active assembly journal in diagnostic mode. The
journal should be a compact event stream, not a Python object graph:

```text
OccurrenceCreated
CandidateSelected
CandidateRejected
EdgeAttached
BindingApplied
RecordSatisfied
DiagnosticRaised
```

Normal assembly may keep this disabled or bounded. On failure or explicit debug
request, the Python facade can format the journal into a human-readable trace.

## Template Model

`astichi.compile(...)` should register a lower template and return a
lower-backed composable facade. The returned object may stay
`BasicComposable`-compatible for migration, but its authoritative payload is a
lower `template_id`, not a CPython AST object.

```text
TemplateDescriptor:
  template_id
  source_template_ref
  static_inventory
  target_index
  production_index
  identifier_demand_index
  external_bind_index
  scope_index
  locator_table
```

The Python lower engine may store a Python AST reference as `source_template_ref`
while it is the reference implementation. A native lower engine should parse
source with its native parser and wrap the resulting native AST/IR template in a
lower-backed composable facade.

Copied CPython AST nodes, rendered source, and executable ASTs are explicit
artifact outputs:

```text
composable.to_python_ast_copy()
composable.to_source()
composable.to_executable_ast()
```

Those artifact paths are valid for tests, goldens, and final output. They are
not the assembly hot path and should not be required for candidate lookup,
inventory merge, or occurrence application.

The static inventory is immutable. It describes records as they exist inside one
unattached template. When a template is inserted into an assembly, the lower
engine creates an occurrence view that remaps this static inventory under a
build path and owner scope.

## Occurrence Model

An occurrence is one placed instance of a template.

```text
Occurrence:
  occurrence_id
  template_id
  build_path
  owner_occurrence_id
  owner_scope_id
  overlay_id
  live_record_set
```

Occurrences are cheap. Creating one should not clone the AST or materialize
Python `InventoryRecord` objects. It prefixes/remaps static inventory records
into the assembly state and updates lookup indexes.

Bindings are overlays on occurrences:

```text
OccurrenceOverlay:
  external_bindings: record_id -> external_slot_id
  identifier_bindings: record_id -> string_id
  keep_names
  satisfied_records
```

This overlay is the copy-on-write unit. Applying an external or identifier bind
updates overlay state and indexes for the affected occurrence. It should not
rebuild the underlying template.

## Inventory As Assembly State

The lower inventory is a mutable or copy-on-write data structure with indexed
records.

Record fields should be compact and stable:

```text
InventoryRecordCore:
  record_id
  template_record_id
  occurrence_id
  kind_id
  logical_name_id
  build_path_id
  owner_scope_id
  shape_id
  source_locator_id
  flags
```

The engine maintains indexes such as:

```text
hole_name -> record ids
production_name -> record ids
identifier_demand_name -> record ids
external_bind_name -> record ids
build_path prefix -> record ids
build_path_id -> record ids
owner scope -> record ids
kind -> record ids
live/satisfied/deleted bitsets
```

These indexes are the authoritative candidate selection surface. Python
`Inventory` becomes a slow projection:

```text
snapshot_debug_inventory(assembly_id) -> Python Inventory
```

That projection can allocate Python records, sort maps, and format diagnostics.
It must not be required for normal assembly.

## Scope Operations

The lower engine should provide primitive operations that match the current
scope workflow.

```text
create_template(static_descriptor) -> template_id
create_scope(root_template_id, root_name) -> assembly_id
fork_scope(assembly_id) -> assembly_id
find_candidates(assembly_id, resource_descriptor, selector) -> candidate ids
apply_candidate(assembly_id, candidate_id) -> apply result
merge_occurrence(assembly_id, target_record_id, template_id, build_name, order)
bind_identifier(assembly_id, record_id, identifier_id)
bind_external(assembly_id, record_id, external_slot_id)
satisfy_record(assembly_id, record_id)
snapshot_debug_inventory(assembly_id) -> debug snapshot
build_materialization_plan(assembly_id) -> materialization plan
```

`find_candidates(...)` should not call back into Python inventory maps. It
should query lower-engine indexes.

`apply_candidate(...)` should not clone AST. It should add occurrences, attach
edges, update overlays, and update indexes.

`build_materialization_plan(...)` returns a deterministic materialization plan
owned by the lower materialization/hygiene API.

`fork_scope(...)` is not required for the first milestone unless a concrete
caller appears. It remains in the model because COW inventory state should make
speculative assembly and verification cheap later.

## Resource Descriptors

Resources also need lower-level descriptors.

```text
ComposableResourceDescriptor:
  template_id
  build_name_id
  build_index
  order
  production_signature

ExternalValueResourceDescriptor:
  external_slot_id

IdentifierResourceDescriptor:
  identifier_id
```

For external values, the lower engine does not need to own arbitrary Python
objects. It only needs an opaque slot id and enough debug metadata to format
errors. The Python facade keeps the actual runtime object table.

For identifiers, the lower engine should intern names and validate identifier
shape at the facade boundary or in the lower engine reference implementation.

## Lower-Owned Materialization And Hygiene

Materialization and hygiene are lower-layer responsibilities. There is no later
handoff from a facade-owned implementation. The Python lower engine implements
them first so the design can be validated before any native extension exists.
If a native engine is adopted, native code owns the same materialization and
hygiene contract.

The facade may still receive Python-facing artifacts from the lower engine:

- `ast.Module` objects for `to_executable_ast()`;
- source strings for emit surfaces;
- `BasicComposable`-compatible facade objects;
- structural verification snapshots.

Those artifacts are lower-engine outputs. Python type adaptation must not move
materialization ownership into the facade.

The materialization contract connects assembly state back to AST/source
templates and symbol metadata.

```text
MaterializationPlan:
  root_occurrence_id
  occurrences
  edges
  overlays
  ordering
  locator_table
  scope_graph
  symbol_table
  hygiene_decisions
  marker_gates
```

The lower engine performs or plans:

1. AST/source template replication for occurrences;
2. external and identifier overlay lowering;
3. child contribution insertion according to edge order;
4. scope graph construction;
5. hygiene analysis and rename decisions;
6. materialize gates for unresolved markers and duplicate final forms;
7. final artifact construction for executable AST, emitted source, or facade
   composable output.

The Python lower-engine implementation may reuse existing `materialize/api.py`
mechanics, but only behind the lower-engine API. That reuse is an implementation
detail; facade code must not drive materialization or hygiene directly.

The native implementation may parse and transform a native AST/IR, then
construct Python `_ast` objects through the CPython API only at the final
artifact boundary. It may also emit source text or produce another validated
artifact accepted by the facade. The API must not expose per-node native
wrappers or require Python to drive materialization record by record.

Native artifact emission must populate required fields, default/list/context
fields, and source-location metadata explicitly enough for the supported Python
versions. Constructor deprecation warnings should be treated as compatibility
failures, since newer Python versions harden incomplete or unknown AST fields.

The materialization plan should reference template ids, locator ids,
occurrence ids, overlay ids, scope ids, and symbol ids. It should not reference
Python AST nodes directly as its durable representation.

## Materialization Coverage

The lower metadata must be rich enough to reproduce current Astichi materialize
semantics. Phase 1 and Phase 2 do not need to implement plan-oriented
materialization fully, but template registration must not lose the metadata Phase 3 will
need.

| Feature family | Required lower-plan data | Required by |
| --- | --- | --- |
| Block holes and block inserts | target record ids, source occurrence ids, order, ref-path locators, fallback selection state | Phase 2 metadata, Phase 3 materializer |
| Expression inserts | expression payload locator, target record id, order, pyimport metadata | Phase 2 metadata, Phase 3 materializer |
| Function-parameter holes | target function locator, parameter payload locator, order, duplicate-name context | Phase 2 metadata, Phase 3 materializer |
| Elif targets | if-chain locator, clause payload locator, order, right-fold placement metadata | Phase 2 metadata, Phase 3 materializer |
| Defaulted block holes | fallback body locator, filled/unfilled state, selected branch metadata | Phase 2 metadata, Phase 3 materializer |
| Identifier bindings | occurrence overlay, inner name id, resolved outer name id, boundary import/pass metadata | Phase 2 apply, Phase 3 lowering |
| External bindings | occurrence overlay, external slot id, target record id, final Python object table key | Phase 2 apply, Phase 3 lowering |
| Pyimport handling | managed import descriptors, scope locator, final import placement metadata | Phase 2 metadata, Phase 3 materializer |
| Comments | marker locator and preservation/strip policy | Phase 3 materializer |
| Scope isolation and hygiene | scope ids, owner relationships, keep names, explicit import/pass/export records | Phase 2 metadata, Phase 3 hygiene/materializer |
| Final gates | unresolved mandatory marker ids, duplicate parameter/name contexts, executable marker strip policy | Phase 3 materializer |

Phase 3 acceptance should include structural verification coverage and final
artifact coverage for each marker family that the current materializer supports.
This matrix exists to prevent a narrow scope prototype from choosing locators
that cannot later express the full materialization contract.

## Structural Verification Layer

Intermediate verification should no longer depend on Python AST output as the
primary snapshot format. The current AST-based intermediate goldens are clever,
but they force inserted elements and assembly state through the slow
materialization representation.

The new verification layer should use a canonical structural format that mirrors
the lower-engine state:

```text
AssemblySnapshot:
  templates:
    - template_id
      source_locator_summary
      static_record_ids
      target_index
      scope_index
  occurrences:
    - occurrence_id
      template_id
      build_path_id
      owner_scope_id
      overlay_id
  records:
    - record_id
      kind
      logical_name
      build_path
      owner_scope
      live/satisfied
  edges:
    - target_record_id
      source_occurrence_id
      order
  overlays:
    - occurrence_id
      identifier_bindings
      external_bindings
      keep_names
  hygiene:
    - scope_id
      bindings
      imports
      exports
      rename_decisions
  materialization:
    - insert_plan
      marker_gates
      artifact_hashes
```

The format should be deterministic, text-friendly, and path-stable. It may be
JSON, line-oriented records, or another canonical text format, but it must avoid
absolute filesystem paths and Python object reprs that vary by process.

Existing final-output goldens remain useful for executable/source behavior. The
new structural snapshots replace intermediate AST goldens for assembly,
inventory, materialization plan, and hygiene verification.

## Debug And Public Inventory Projection

Current tests and user surfaces inspect inventory. Those remain useful, but
they should not define the internal representation.

The lower engine should expose a deterministic debug snapshot:

```text
DebugInventorySnapshot:
  records
  maps
  source locators
  build paths
  owner scopes
  satisfaction state
```

The Python facade converts that into current `Inventory`,
`InventoryRecord`, descriptor, and diagnostic objects.

This means:

- printing inventory is allowed to be slower;
- descriptor APIs stay stable;
- diagnostics remain precise;
- tests can compare projected inventory against existing expectations;
- hot assembly avoids Python object allocation and repeated map freezing.

## Diagnostics Contract

Diagnostic quality is part of the compatibility contract. The lower engine must
carry enough compact data to reproduce current error context:

```text
source_locator_id
template_id
template_record_id
occurrence_id
build_path_id
owner_scope_id
logical_name_id
kind_id
```

The facade resolves those ids lazily when an error is formatted or a debug
snapshot is requested. Missing-candidate and ambiguous-candidate errors should
continue to identify demand records, resource records, build paths, owners, and
source locations.

Golden diagnostic text may change only when the new wording is intentionally
better and the corresponding tests/docs are updated. Error timing should remain
as close as possible to the current API. If a validation moves from assembly to
materialization, that timing change must be explicit in the phase notes.

## Validation Timing Contract

The lower engine should preserve current validation timing unless a phase
explicitly changes it.

| Validation family | Current timing target | Lower-engine timing |
| --- | --- | --- |
| Source marker shape and parse errors | compile/template registration | template registration |
| Target-site existence for registered templates | builder target/add/apply | template metadata lookup during assembly |
| Candidate missing/ambiguous | `find_candidates`/`require_one` before apply | lower-engine candidate lookup before apply |
| Resource-target compatibility | candidate selection/apply | lower-engine structural check plus semantic compatibility table/callback |
| External/identifier unknown or conflicting bind | bind/apply | overlay update during apply |
| Repeated same-site binding collapse | YIDL `_binding_candidate` behavior | candidate result grouping or equivalent YIDL adapter |
| Unresolved mandatory holes/markers | current materialization step | lower materialization |
| Duplicate final parameter names | current materialization step | lower materialization |
| Hygiene collisions and keep-name enforcement | current materialization step | lower hygiene/materialization |
| Pyimport placement and marker stripping | current materialization step | lower materialization |

If an implementation moves a row to a different phase, the phase plan must name
the change and update diagnostics tests deliberately.

## Why This Is Native-Ready

The proposed lower layer is native-ready because the hot operations are expressed
as id/index operations over compact records:

- occurrence allocation;
- static inventory prefix/remap;
- candidate lookup;
- target/resource compatibility checks;
- binding overlays;
- record satisfaction;
- deterministic ordering;
- debug snapshot construction.

The Python facade does not need to know whether these operations are executed by
the Python reference engine or a native extension.

The native implementation should not expose native record objects directly as
the primary API. It should expose opaque handles and bulk snapshot/plan
transfer. Per-record Python wrapping would reintroduce object churn at the
boundary.

The native backend may also avoid CPython AST objects as its working graph. A
native parser plus native AST/IR transform path can instantiate CPython
`ast`/`_ast` nodes only at the final materialized artifact boundary, where
Python can call `compile(...)` and `exec(...)` normally.

## Migration Plan

### Pre-Phase 0: API Surface Pruning

Before lower-engine code changes, prune unused assembly APIs and narrow the
supported surface to the YIDL integration contract plus required validation
surfaces.

This phase should:

- inventory current `astichi.assembler.scope` and builder APIs used by YIDL;
- mark unused assembly APIs as removable or adapter-only;
- update YIDL callers where a smaller lower-engine API is clearer;
- remove or quarantine tests that only preserve obsolete assembly API shape;
- keep semantic behavior coverage through YIDL integration tests, structural
  snapshots, and final artifact tests.

Acceptance:

- the supported assembly API surface is documented in this proposal or the
  active summary;
- unused assembly APIs are removed or explicitly marked out of the refactor
  path;
- no lower-engine prototype work depends on preserving obsolete API shape.

### Phase 0: Counters And Baseline

Before replacing behavior, add or reuse lightweight counters around the current
hot path:

- `scope.apply` by candidate type;
- `BasicComposable.bind_identifier`;
- `BasicComposable.bind`;
- `_rebuild_composable`;
- `_replace_occurrence_inventory`;
- target-site validation;
- `materialize_composable`;
- final import wall time for the 8-class lifecycle workload.

Also add counters for likely new failure modes:

- lower-engine candidate lookup count/time;
- debug inventory projection count/time;
- materialization-plan generation count/time;
- build-only adapter or legacy builder translation count/time, if any;
- materialization-plan construction and consumption count/time;
- diagnostic snapshot/journal formatting count/time.

Acceptance:

- a checked-in validation command reports counts and timings without cProfile;
- the baseline confirms the same shape described in
  `dev-docs/AstichiPerfAnal.md`.

### Phase 1: Lower Engine Reference Model

Add a Python lower-engine module with the explicit template, occurrence,
inventory, candidate, materialization, hygiene, and structural snapshot APIs.
Keep it internal.

Acceptance:

- small scope assembly tests pass against the new engine;
- record ids use `(occurrence_id, template_record_id)`;
- build paths go through `build_path_id` handles;
- target metadata is precomputed at template registration;
- `find_candidates` can query lower indexes;
- debug snapshots project to current `Inventory`;
- structural snapshots represent lower-engine intermediate state without AST
  materialization;
- materialization and hygiene API ownership is in the lower engine, even when
  only a subset is implemented;
- no YIDL-facing behavior changes.

### Phase 2: Route `AssemblyScope` Through Lower Engine

Change `AssemblyScope` so add/apply/find-candidate operations use lower-engine
indexes. Keep `scope.inventory` as a projected snapshot.

Phase 2 should not begin as a broad route-through until:

- Phase 0 counters include bridge and projection costs;
- Phase 1 has lower-index candidate lookup and debug inventory projection;
- the materialization coverage matrix has been checked against current marker
  families;
- the validation timing table has an explicit owner for each diagnostic family.

#### Phase 2 State Invariant

After `AssemblyScope.add(...)`, the lower engine is authoritative for candidate
lookup and apply-time assembly state.

`scope.apply(...)` must not mutate the old builder graph as a second source of
truth. It may record only minimal, measured compatibility data needed by a
temporary `scope.build()` adapter, and that adapter cost must be reported
separately. If the adapter starts reconstructing full old builder state or
masking semantic drift, Phase 2 should stop and move directly to Phase 3.

The preferred bridge is:

1. lower state owns add/apply/candidate lookup;
2. `scope.inventory` returns a projected debug snapshot only when requested;
3. `scope.build()` either consumes a lower materialization plan directly or uses a
   narrow, throwaway build-only adapter whose cost is not counted as apply-path
   success.

Acceptance:

- existing assembler scope tests pass;
- YIDL lifecycle import still produces equivalent classes;
- counters show no per-apply AST clone/rebuild path;
- counters show no `_rebuild_composable` calls during assembly apply;
- counters show no `_replace_occurrence_inventory` calls on the hot path;
- candidate lookup does not require projecting full Python `Inventory`.

### Phase 3: Lower-Owned Materialization And Hygiene

Move materialization and hygiene execution behind the lower-engine API instead
of reconstructing intent from the builder graph and Python inventory. In the
Python lower-engine implementation this may wrap/reuse existing materializer
internals, but the owner and API boundary are lower-layer from the start.

Acceptance:

- structural materialization/hygiene snapshots cover current marker families;
- final materialized outputs remain equivalent unless intentionally updated;
- executable AST parity tests pass;
- old facade-driven materialization calls disappear from the hot path;
- materialization call count and AST traversal count drop.

### Phase 4: Public Bind Batching And Lower Overlay Materialization

Phase 2 owns the hard guarantee that `AssemblyScope.apply(...)` does not rebuild
composables per binding. Phase 4 is for remaining non-scope surfaces and
materialization efficiency:

- keep public or YIDL-used `BasicComposable.bind(...)` /
  `bind_identifier(...)` behavior correct, or update YIDL callers if those APIs
  intentionally change;
- batch overlay lowering per occurrence during materialization;
- preserve current diagnostics for unknown or conflicting binds.

Acceptance:

- `BasicComposable.bind(...)` and `bind_identifier(...)` remain correct;
- scope assembly still does not rebuild composables per binding;
- lifecycle import profile shows binding rebuilds disappear from the hot path.

### Phase 5: Native Engine Spike

Implement the lower-engine API in native code behind the same facade. Do this
only after the Python lower engine proves the API boundary and exposes a
remaining measured bottleneck worth moving. The native backend may be Rust,
C++, or a hybrid module.

Acceptance:

- same tests pass against Python and native engines;
- engine selection is opt-in;
- debug snapshots match;
- perf profile shows Python time has moved out of candidate selection,
  inventory merge, materialization, and hygiene.

Suggested gate:

- Python lower engine is functionally complete through Phase 4; and
- the 8-class lifecycle workload remains above the intermediate budget, such as
  50 ms/class, with inventory, matching, materialization, or hygiene still
  visible in the profile;
- lower-owned materialization and hygiene are implemented in Python and covered
  by structural snapshots;
- memory behavior is understood for string interns, build-path tables, source
  locator tables, template registries, and external-slot registries;
- teardown/lifetime ownership is defined for per-scope, per-template, and
  process-global tables.

## Performance Estimate

These estimates are guesses, but they are grounded in the current profile shape.
The current YIDL lifecycle import path spends about 5.27 s decorating 8 classes,
or about 659 ms per class. Assembly alone is about 575 ms per class.

### Expected Python Reference Engine Gains

| Change | Expected effect | Confidence |
| --- | ---: | --- |
| Inventory-first scope apply, no per-apply AST rebuild | 5x to 20x assembly speedup | medium |
| Lower-engine candidate indexes instead of Python inventory projections | 2x to 5x additional assembly speedup | medium |
| Batched binding overlays | 2x to 8x additional binding-heavy speedup | medium-high |
| Lower-owned materialization and hygiene | 2x to 5x materialization speedup | medium |

Combined, a pure-Python version of this architecture could plausibly reduce the
representative lifecycle import from about 5.3 s to the 100 ms to 500 ms range.
That is roughly a 10x to 50x improvement.

These multipliers are not independent. The estimate is a planning range, not a
schedule promise. The lower end assumes Python object allocation and final AST
construction remain noticeable. The upper end assumes most repeated
marker/inventory/hygiene work is removed from the per-class path.

### Expected Native Engine Gains

If the lower engine moves to native code and avoids per-record Python wrapping
during assembly, materialization, and hygiene, the hot lower layer could
plausibly improve another 5x to 20x over the Python reference engine.

For the representative lifecycle import, that suggests:

| Implementation | Import-time decorator work for 8 classes | Per class |
| --- | ---: | ---: |
| Current | ~5.3 s | ~659 ms |
| Python lower engine | ~100-500 ms | ~12-62 ms |
| Native lower engine plus Python facade adapter | ~25-150 ms | ~3-19 ms |
| Native lower engine plus optimized artifact/cache path | ~8-50 ms | ~1-6 ms |

Sub-millisecond per class is unlikely from this refactor alone if every class
still materializes a full Python AST and compiles it independently. A strict
sub-millisecond target probably requires one or more of:

- reusing compiled code objects for repeated structural shapes;
- generating a module-level factory once and calling it for each harvested class;
- moving more materialized artifact construction below the Python object boundary;
- avoiding full Python AST materialization on cache hits.

The realistic near-term target is not sub-millisecond. It is to remove the
seconds-scale assembly cost and make the remaining cost visible enough to choose
the next boundary deliberately.

### Phase Metrics

Phases should be gated by counters, not only wall-time ranges:

| Phase | Counter target |
| --- | --- |
| Phase 2 | zero `BasicComposable.bind_identifier` / `bind` calls during `scope.apply` |
| Phase 2 | zero `_rebuild_composable` calls during assembly apply |
| Phase 2 | zero `_replace_occurrence_inventory` calls on the hot path |
| Phase 2 | candidate lookup avoids projected Python `Inventory` |
| Phase 3 | materialization and hygiene execute through the lower-engine API |
| Phase 3 | structural materialization/hygiene snapshots replace intermediate AST goldens |
| Phase 4 | identifier/external overlays lower in batches per occurrence |
| Phase 5 | native engine uses bulk snapshots/plans, not per-record wrappers |

## Risks

### Semantic Drift

The lower engine must not redefine Astichi semantics. Existing source,
materialize, emit, descriptor, and diagnostic tests remain the contract.

Mitigation:

- keep Python reference engine behavior-first;
- run existing tests through the facade;
- add dual-engine parity once the native implementation exists.

### Debug Projection Hides Bugs

If Python `Inventory` becomes a projection, bugs can hide in the conversion
boundary.

Mitigation:

- compare lower snapshots to current inventory on small graphs;
- keep deterministic record ids and ordering;
- test diagnostics from projected records.

### Materialization Remains Hot

Moving assembly into inventory may expose materialization as the next dominant
cost.

Mitigation:

- profile materialization separately after Phase 2;
- keep materialization structures compact;
- batch overlay lowering;
- add cache/code-object strategy only after the new assembly cost is measured.

### Native Boundary Chatter

If Python calls into native code per record, the boundary cost will erase much of the
gain.

Mitigation:

- bulk operations;
- opaque handles;
- bulk debug snapshots;
- bulk materialization plans.

### Dual-Engine Maintenance

Once a native engine exists, semantic fixes may need to land in both the Python
reference engine and native engine until one becomes clearly primary.

Mitigation:

- delay the native spike until the Python boundary is stable;
- keep generated semantic tables where possible;
- run parity tests against both engines;
- avoid adding second-engine behavior before the first engine's counters prove
  the design.

### No-Op Edge Cost Remains

After assembly and inventory merge become fast, YIDL no-op edge evaluation may
become visible.

Mitigation:

- measure edge/contribution selection after Phase 2;
- pre-filter YIDL apply edges by available collections and field kinds when it
  is semantically safe;
- treat this as a YIDL runtime-plan optimization, not an inventory-engine
  responsibility.

## Remaining Open Questions

1. What engine-selection surface should tests use once both Python and native
   implementations exist?
2. Which compatibility checks can be generated into lower semantic tables, and
   which must continue to call Python descriptor behavior?
3. Should the debug assembly journal be always-on with a bounded buffer, or only
   enabled by diagnostic mode?
4. What intermediate budget should gate the native spike?

## Recommended Next Step

First prune unused assembly APIs. Then implement Phase 0 counters and a small
Python lower-engine prototype for `AssemblyScope` plus the structural
verification snapshot format. Do not let the broad Phase 2 concerns block these
steps; use them to constrain the prototype and define the next gate.

Do not start by porting every materialization feature. The first proof point
should be:

- register a root template;
- insert composable occurrences;
- apply external and identifier binds as overlays;
- satisfy single-add holes;
- query candidates from lower indexes;
- project inventory for existing tests;
- emit a deterministic structural snapshot that represents assembly state
  without using AST output as the intermediate format;
- execute the prototype materialization/hygiene subset through the lower layer,
  even when that subset is small.

If that prototype removes the current `scope.apply` and inventory hot paths
without changing YIDL-facing behavior, the architecture is validated enough to
expand materialization/hygiene coverage and then consider native code behind the same
boundary.
