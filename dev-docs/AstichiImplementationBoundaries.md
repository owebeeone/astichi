# Astichi implementation boundaries

This document defines execution-layer boundaries for Astichi implementation.

It is not the API specification. It is an implementation-structure rule for how
the V1 design must be built and tested.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md`
- `astichi/dev-docs/AstichiV1Milestones.md`
- `astichi/dev-docs/IdentifierHygieneRequirements.md`

## 1. Rule

Astichi implementation must be layered.

Do not implement Astichi as one blended subsystem that simultaneously parses,
classifies, builds, materializes, emits, and restores provenance in one pass.

Each layer must have:

- a clear input
- a clear output
- a testable boundary
- a limited dependency surface on earlier layers only

Later layers may depend on earlier layers. Earlier layers must not depend on
later layers.

## 2. Required implementation layers

### 2.1 Compile / lowering

This layer owns:

- parsing source into Python AST
- recognizing Astichi markers
- capturing source-origin metadata
- inferring marker shape from AST context

This layer outputs:

- parsed AST
- recognized marker records
- lowered marker metadata suitable for later classification

This layer must not depend on:

- builder graph implementation
- materialization
- source emission
- provenance payload restoration

Primary tests:

- marker recognition
- valid/invalid marker placement
- AST-context shape inference
- compile-origin metadata capture

### 2.2 Name classification / hygiene

This layer owns:

- local/generated binding discovery
- explicit keep handling
- explicit external handling
- preserved-name handling
- strict/permissive unresolved-name handling
- hygienic renaming

This layer outputs:

- classified names
- rewritten/lowered AST or equivalent internal structure with hygiene applied
- implied-demand records where permitted

This layer must not depend on:

- builder graph composition
- materialization
- source emission

Primary tests:

- strict vs permissive behavior
- keep-name preservation
- collision handling
- hygienic rename correctness

### 2.3 Composable / ports

This layer owns:

- immutable `Composable` construction
- demand port construction
- supply port construction
- compatibility metadata

This layer outputs:

- a valid immutable `Composable`
- explicit demand/supply port collections
- compatibility information sufficient for composition validation

This layer must not depend on:

- builder graph execution
- source emission
- provenance payload restoration

Primary tests:

- correct port extraction
- correct supply/demand exposure
- compatibility validation failures

### 2.4 Builder / addressing

This layer owns:

- instance registration
- root-instance-first addressing
- loop-expanded addressing handles when available
- additive edge registration
- ordering state
- fluent API and raw API over the same graph semantics

This layer outputs:

- a mutable builder graph
- stable builder/instance/target handles
- deterministic additive edges

This layer must not depend on:

- source emission
- provenance payload restoration

This layer may depend on:

- immutable `Composable`
- port/compatibility metadata

Primary tests:

- instance creation
- target addressing
- additive edge recording
- ordering conflict detection
- fluent/raw API equivalence

### 2.5 Build / materialize

This layer owns:

- `build()` merging into a new `Composable`
- preservation of unresolved holes/loops where appropriate
- loop unrolling where requested/permitted
- final compatibility enforcement
- final hygiene enforcement
- final lowering into a runnable/emittable AST/artifact

This layer outputs:

- built `Composable`
- materialized runnable/emittable artifact

This layer may depend on:

- compile/lowering output
- classification/hygiene output
- composable/ports
- builder graph

Primary tests:

- build leaves unresolved boundaries open
- non-unrolled loops remain loops
- supported loops unroll correctly
- materialize rejects incompatible or incomplete inputs
- end-to-end additive composition

### 2.6 Emit / provenance

This layer owns:

- source emission
- optional provenance payload emission
- round-trip provenance restoration checks

This layer outputs:

- source text
- optional `astichi_provenance_payload("...")`

This layer must not define snippet semantics.

Snippet semantics must always be rediscovered by reparsing the source itself.

Primary tests:

- plain emission
- emission with provenance
- successful provenance restoration on matching source
- hard failure on edited/non-matching AST shape

## 3. Boundary rules

### 3.1 No backward semantic leakage

Earlier layers must not depend on decisions owned by later layers.

Examples of forbidden coupling:

- compile/lowering requiring builder handles to exist
- hygiene depending on emitted-source policy
- composable construction depending on provenance payload format

### 3.2 No hidden semantic payloads

Emission/provenance must not become a hidden semantic transport.

The emitted payload may restore AST/provenance information only.

Marker semantics, holes, binds, inserts, and exports must be rediscovered from
the source on reparse.

### 3.3 Additive-first implementation

Phase 1 implementation must stay additive-first.

Do not implement replacement semantics, deep descendant traversal, or other
non-V1 extensions early just because the code structure could be generalized.

### 3.4 Testing at the owning layer

Each behavior should first be tested at the layer that owns it.

End-to-end tests are required, but they do not replace layer-local tests.

## 4. Handoff artifacts

Each layer should expose a concrete artifact that the next layer can consume.

Examples:

- compile/lowering: marker-bearing lowered AST + marker records
- hygiene: classified/hygienic lowered structure
- composable: immutable `Composable` + ports
- builder: builder graph + handles
- build/materialize: built `Composable` or materialized artifact
- emit: source text + optional provenance payload

These handoff artifacts should be inspectable in tests.

## 5. Implementation guidance

- Prefer direct data structures over prematurely abstract frameworks.
- Keep the raw/assembler API boring and explicit.
- Keep the fluent API shallow; it is a DSL over the raw API, not a second
  semantic engine.
- If a design question arises during implementation, first identify which layer
  owns the question before changing code.

## 6. Exit rule

Before work is considered complete for a milestone or sub-phase, it should be
possible to state:

- which layer owns the implemented behavior
- what artifact it produces
- how that artifact is validated independently of later layers

If that cannot be stated clearly, the implementation has probably crossed
boundaries and should be corrected.
