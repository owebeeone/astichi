# Engine Selection Contract

Status: Slice 14b boundary contract, updated for the required native lower
engine.

The Python lower engine is the first implementation and is the correctness
reference. The production native lower engine is now required and may be Rust,
C++, or a hybrid module. It must run behind the same facade and the same
structural golden harness.

## Selection Rules

The facade should select one lower engine at scope creation:

```text
python: reference implementation and explicit fallback
native: production native implementation when available and compatible
native-rust: explicit Rust-backed implementation, if shipped
native-cpp: explicit C++-backed implementation, if shipped
auto: use native only when the active bundle and platform pass compatibility gates
```

The exact public spelling can be finalized in the native spike, but selection
must happen at a coarse engine/scope boundary. The hot path must not bounce
between Python and native code per record.

## Compatibility Gates

Before `native` can be selected, the native engine must accept:

- the active surface bundle;
- every registered operation primitive used by the bundle;
- the snapshot schema version;
- the materialization/hygiene ownership contract;
- the external-slot ownership contract.
- the `native.full_lower_engine.current_surfaces.v1` capability.

### Self-native production tier (F0c+)

Hybrid native is not the YIDL lifecycle production target. Per-slice
`native.self_native.*` features are advertised as slices land; production guards
require `native.self_native.current_surfaces.v1`.

| API | Required capabilities | Behavior |
|-----|----------------------|----------|
| `select_lower_engine` | hybrid (`full_lower_engine` + package v2) | Current default; unchanged until F4c enables self-native caps |
| `select_self_native_production_engine` | `native.self_native.current_surfaces.v1` | Lifecycle production path; explicit `native` fails if only hybrid caps exist |

Threading and handle ownership: `FullSelfNativeRustAstPlan-F0c-threading.md`.

If any engine-level gate fails, `auto` falls back before work starts. Explicit
`native` should fail with a diagnostic rather than silently crossing back into
Python per record.

An importable native extension skeleton is not enough. Selection must be based
on declared lower-engine capabilities, not extension import success.

`auto` fallback should be quiet in normal operation but visible in diagnostic
mode through a structured selection event:

```text
EngineSelectionEvent:
  requested_engine
  selected_engine
  fallback_scope
  reason_key
  reason_detail
```

Example:

```text
requested_engine=auto
selected_engine=python
fallback_scope=template
reason_key=native_grammar_unsupported
```

If the native backend uses its own parser and AST IR, it must also accept:

- the supported Python grammar version;
- the native AST-to-CPython AST emission contract;
- the source-location policy required by `compile(...)` and diagnostics;
- the required/default-field population policy for emitted CPython AST nodes;
- the public `ast`/`_ast` plus `compile(...)` artifact boundary.

Internal CPython compiler APIs such as `PyArena` or `_PyAST_Compile` are not
part of the default compatibility contract. A backend that requires them must be
selected explicitly and must have its own version-support spike and maintenance
gate.

## Grammar Fallback Policy

Grammar capability is template-shaped, not just engine-shaped. The selection
policy is:

- `python`: always use the Python lower engine.
- explicit `native`, `native-rust`, or `native-cpp`: fail before template
  registration if the native parser cannot support the host Python grammar or
  the template source shape.
- `auto`: attempt native per template, then fall back to the Python lower engine
  for that whole template when grammar capability fails.

Fallback is never per record and never during candidate lookup. A template is
owned by one engine for its lifetime. Any `auto` fallback must increment a
counter and emit `EngineSelectionEvent` in diagnostic mode so slow-path
selection can be explained.

The native AST probe is successful only if the chosen parser plus this fallback
policy can run all current Astichi `tests/data/gold_src/` fixtures.

## Test Matrix

The same fixture should run against:

- Python lower engine;
- native lower engine;
- `auto` selection when native support is installed.

Structural snapshots compare by stable surface, pattern, and operation keys.
Final-output goldens must pass for the same fixture set. Native implementation
is not considered correct because it is faster; it is correct only when it
matches the Python lower engine through the shared verification path.

## Native Module Boundary

The production native extension should expose a small engine-shaped API. Names
below are contract names, not final Python symbol names. The complete
implementation plan is `NativeLowerEngineDetailedPlan.md`.

```text
engine_capabilities() -> CapabilitySnapshot
engine_create(request: EngineCreateRequest) -> EngineHandle
engine_close(engine: EngineHandle) -> None

register_surface_bundle(engine: EngineHandle, bundle: SurfaceBundleSnapshot)
  -> RegisteredBundleSnapshot

register_template(engine: EngineHandle, template: TemplateRegistrationSnapshot)
  -> TemplateHandle

state_create(engine: EngineHandle) -> StateHandle
state_close(state: StateHandle) -> None

append_occurrence(state: StateHandle, request: OccurrenceAppendRequest)
  -> OccurrenceHandle

append_edges(state: StateHandle, requests: Sequence[EdgeAppendRequest])
  -> EdgeAppendResultBatch

append_overlays(state: StateHandle, requests: Sequence[OverlayAppendRequest])
  -> OverlayAppendResultBatch

query_candidates(state: StateHandle, request: CandidateQueryRequest)
  -> CandidateBatch

materialization_plan_snapshot(state: StateHandle, request: PlanRequest)
  -> MaterializationPlanSnapshot

structural_snapshot(state: StateHandle, request: SnapshotRequest)
  -> StructuralSnapshot

copy_artifact(state: StateHandle, request: ArtifactCopyRequest)
  -> PythonArtifact
```

The boundary is intentionally bulk-shaped. Python may call one native function
for a batch of edges, overlays, or candidate queries, but it must not call
native code once per inventory record or once per pattern branch.

## Handle Model

Native handles are opaque to Python. They may be small integers, tagged integer
tuples, capsules, or extension objects, but every handle must carry enough
identity for stale-handle diagnostics:

```text
engine_epoch
owner_id
kind
index
generation
```

The native engine validates handles at every public boundary. A handle created
by another engine, an already-closed state, or an older generation fails before
work starts. Snapshot output uses stable keys and event-order ids; it must not
depend on native storage addresses.

Handle classes:

- `EngineHandle`
- `BundleHandle`
- `TemplateHandle`
- `StateHandle`
- `OccurrenceHandle`
- `RecordHandle`
- `EdgeHandle`
- `OverlayHandle`
- `ExternalSlotHandle`
- `ArtifactHandle`, if artifact creation becomes multi-step

## Input Shapes

All native inputs are structural snapshots or lowered request records derived
from the same Python dataclasses used by the Python lower engine. The native
module does not receive Python `InventoryRecord` objects on hot paths.

`SurfaceBundleSnapshot` contains:

- bundle key, schema version, and bundle signature;
- ordered surfaces, operations, patterns, and compatibility descriptors;
- dormant-future pattern templates as diagnostic-compatible entries;
- operation primitive support requirements.

`TemplateRegistrationSnapshot` contains:

- template key and source summary;
- ordered template records;
- stable surface keys plus registered surface handles;
- source locator summaries and materialization anchors;
- optional parser/IR reference metadata when native parser registration is
  enabled;
- debug projection metadata only when explicitly requested for snapshots.

`CandidateQueryRequest` contains:

- resource name, inventory kind, target surface handle, and owner selectors;
- overlay/resolved-name view selectors;
- diagnostic mode;
- maximum result policy, if the caller wants early ambiguity reporting.

`CandidateBatch` returns:

- stable candidate keys;
- target/source record handles;
- accepted compatibility policy;
- enough lazy diagnostic metadata for Python formatting;
- no Python inventory projection unless diagnostic mode explicitly asks for it.

## Error Model

Native errors must map to Python exception classes without leaking backend
implementation details. Required error categories:

- schema/version mismatch;
- unsupported operation primitive;
- unsupported grammar or parser feature;
- stale handle;
- closed handle;
- foreign-engine handle;
- invalid state transition;
- ambiguous candidate;
- missing candidate;
- artifact construction failure;
- internal native invariant failure.

Explicit native selection raises on compatibility failure. `auto` selection may
fall back only before template/state work begins, and the fallback must produce
an `EngineSelectionEvent` in diagnostic mode.

## External Values

Python external objects remain Python-owned. Native state stores only
`ExternalSlotHandle` references and lifetime ownership metadata:

```text
external_slot_id
owner_state
resource_name
python_object_ref_policy
single_use_state
```

If the native extension stores a `PyObject` reference, it must own and release
that reference explicitly at state teardown. Candidate lookup and
materialization use slot handles, not direct object copies.

## Native Parser/IR References

If the native parser path is enabled, template registration may attach a native
parser tree or normalized Astichi IR reference to a template. The Python facade
still treats CPython AST/source as explicit artifact copies:

```text
source text -> native parser/IR -> native template tables
native materialized artifact -> CPython ast/_ast copy -> compile(...)
```

Parser/IR references are engine-owned. They are never exposed as public Python
objects, and they must not require internal CPython compiler APIs.

## Feature Negotiation

`engine_capabilities()` returns at least:

- native ABI schema version;
- supported bundle schema versions;
- supported snapshot schema versions;
- supported operation primitives;
- parser backend and grammar version, if any;
- artifact kinds supported;
- whether parsing can run without the GIL;
- whether materialization can run without the GIL;
- build profile and backend label.

Bundle registration rejects unsupported operation primitives up front. Adding a
new Astichi surface does not require a native API change when it can be
expressed with an already-supported operation primitive and compatibility
descriptor.
