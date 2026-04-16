# V1 plan

This document is the execution plan for Astichi V1.

It expands the milestone document into step-by-step implementation work.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md`
- `astichi/dev-docs/AstichiImplementationBoundaries.md`
- `astichi/dev-docs/AstichiInternalsDesignV1.md`
- `astichi/dev-docs/AstichiV1Milestones.md`
- `astichi/dev-docs/V1ProgressRegister.md`

## 1. Plan structure

The plan uses milestone-aligned numbering.

- Milestone 1 uses steps `1a`, `1b`, `1c`, ...
- Milestone 2 uses steps `2a`, `2b`, `2c`, ...
- and so on

This alignment is deliberate. Do not break milestone numbering unless the
milestone document itself changes.

Each step must declare:

- owner layer
- goal
- output artifact
- verification target
- exit rules

Each milestone must declare:

- milestone goal
- milestone-level exit gate

## 2. Global execution rules

- No single implementation step should require more than roughly 400 lines of
  production-code change.
- If a step grows beyond that size, split it into another milestone-aligned
  substep before implementing.
- Each step should first be verified at the layer that owns it.
- Focused tests are required per step unless the step is intentionally
  preparatory and non-behavioral.
- A milestone is not complete merely because its substeps exist; the
  milestone-level exit gate must also pass.

## 3. Milestone 1: Lowering pipeline

Owner layer:

- `frontend`
- `lowering`
- `asttools`

Milestone goal:

- parse source into Python AST
- recognize V1 markers
- capture compile-origin metadata
- infer marker shape from AST context

Milestone 1 exit gate:

- `astichi.compile(...)` entrypoint exists
- marker recognition is implemented for the V1 marker surface
- compile-origin metadata is carried through lowering
- AST-context shape inference works for scalar, `*`, and `**` cases
- focused lowering tests pass
- full test suite passes

### 1a. Compile entrypoint skeleton

Owner layer:

- `frontend`

Goal:

- establish the public `astichi.compile(...)` entrypoint as a real frontend
  function rather than a stub

Output artifact:

- frontend compile wrapper that accepts:
  - source
  - file name
  - line number
  - offset

Verification target:

- focused tests for argument intake and basic parse success/failure
- verify file name, line number, and first-line column details are correctly
  allocated to parsed AST nodes

Implementation rule:

- do not rebase AST line numbers by walking the parsed tree in this step
- implement source-origin positioning by constructing padded parse input:
  - prepend `line_number - 1` newlines
  - prepend `offset` spaces before the first logical source line
  - pass `file_name` directly to `ast.parse(..., filename=file_name)`

Exit rules:

- compile entrypoint is implemented
- origin metadata parameters are accepted and stored in a frontend-owned
  structure
- at least one parse-success and one parse-failure test exist
- tests verify the padded-source origin behavior
- focused tests pass

### 1b. Marker recognition

Owner layer:

- `lowering`

Goal:

- recognize the V1 source marker surface in parsed AST

Output artifact:

- marker-recognition visitor/walker
- marker records for:
  - `astichi_hole`
  - `astichi_bind_once`
  - `astichi_bind_shared`
  - `astichi_bind_external`
  - `astichi_keep`
  - `astichi_export`
  - `astichi_for`
  - `@astichi_insert`

Verification target:

- focused marker-recognition tests over representative source snippets

Implementation rule:

- marker recognition in this step is purely syntactic
- recognize only bare-name call/decorator forms
- use one centralized marker registry keyed by reserved source marker names
- preferred shape:
  - `dict[str, MarkerSpec]`
  - mapping source name -> behavior-bearing marker capability/singleton object
- registry values should be behavior-bearing marker singleton/spec objects, not
  passive tag enums
- do not support alias resolution, attribute access, or runtime lookup in this
  step

Exit rules:

- every V1 marker is recognized
- recognized marker names/targets are extracted correctly
- invalid marker shapes fail clearly
- focused tests pass

### 1c. AST-context shape inference

Owner layer:

- `asttools`
- `lowering`

Goal:

- infer hole/use shape from valid Python AST context

Output artifact:

- shape-inference helpers and lowering metadata for:
  - scalar expression position
  - positional variadic expansion via `*`
  - named variadic expansion via `**`
  - standalone block-position hole statements

Verification target:

- focused tests for shape inference from parsed AST structure

Exit rules:

- scalar, `*`, and `**` shapes are inferred correctly
- unsupported contexts fail early
- focused tests pass

## 4. Milestone 2: Name classification and hygiene

Owner layer:

- `hygiene`

Milestone goal:

- classify identifiers
- implement strict/permissive handling
- implement hygienic renaming

Milestone 2 exit gate:

- classification order is implemented
- keep-name preservation works
- strict/permissive behavior is test-covered
- collision handling is correct
- focused hygiene tests pass
- full test suite passes

### 2a. Classification pass

Owner layer:

- `hygiene`

Goal:

- implement the classification order for names in lowered snippets

Output artifact:

- classification routine producing:
  - local/generated bindings
  - kept/preserved names
  - explicit externals
  - unresolved free identifiers

Verification target:

- focused classification tests

Exit rules:

- classification order matches V1
- classification output is inspectable in tests
- focused tests pass

### 2b. Strict vs permissive handling

Owner layer:

- `hygiene`

Goal:

- support strict and permissive unresolved-name behavior

Output artifact:

- mode-aware classification/validation behavior

Verification target:

- focused tests covering:
  - strict-mode hard failure
  - permissive-mode implied demands

Exit rules:

- strict mode errors on unresolved free identifiers
- permissive mode promotes unresolved free identifiers to implied demands
- focused tests pass

### 2c. Hygienic renaming

Owner layer:

- `hygiene`

Goal:

- rename local/generated bindings safely against preserved names and collisions

Output artifact:

- hygienic renaming transformer or equivalent rewritten structure

Verification target:

- focused rename/collision tests

Exit rules:

- kept names preserve spelling
- colliding locals are renamed correctly
- resulting lowered structure is inspectable in tests
- focused tests pass

## 5. Milestone 3: Ports and composable carrier

Owner layer:

- `model`

Milestone goal:

- define immutable `Composable`
- extract demand/supply ports
- implement compatibility validation

Milestone 3 exit gate:

- compiling/lowering can produce a valid immutable `Composable`
- demand/supply ports are inspectable
- compatibility validation exists and rejects invalid pairings
- focused model tests pass
- full test suite passes

### 3a. Demand and supply port structures

Owner layer:

- `model`

Goal:

- define the immutable port structures and related metadata

Output artifact:

- demand-port type(s)
- supply-port type(s)
- basic compatibility metadata structures

Verification target:

- focused model/structure tests

Exit rules:

- port structures exist and are immutable by design
- demand vs supply roles are explicit
- focused tests pass

### 3b. Port extraction

Owner layer:

- `model`

Goal:

- map lowered/classified marker structures into demand/supply ports

Output artifact:

- port extraction logic
- inspectable port collections on a compiled snippet

Verification target:

- focused tests compiling snippets and inspecting resulting ports

Exit rules:

- holes/implied demands become demand ports
- exports become supply ports
- extracted ports are inspectable in tests
- focused tests pass

### 3c. Compatibility validation and `Composable`

Owner layer:

- `model`

Goal:

- finalize compatibility checks and bind them into immutable `Composable`

Output artifact:

- `Composable` implementation or concrete backing carrier
- compatibility validators for:
  - placement
  - constness/mutability
  - scalar vs variadic shape

Verification target:

- focused compatibility tests
- focused composable-construction tests

Exit rules:

- valid snippets yield valid `Composable` instances
- invalid pairings hard-fail
- compatibility checks are enforced
- focused tests pass

## 6. Milestone 4: Builder graph and additive wiring

Owner layer:

- `builder`

Milestone goal:

- add named instances
- implement root-instance-first handles
- implement additive edges and order validation
- expose fluent and raw APIs

Milestone 4 exit gate:

- builder can register named instances
- root-instance-first addressing works
- additive edges are inspectable
- order validation works
- fluent and raw APIs are equivalent for covered cases
- focused builder tests pass
- full test suite passes

### 4a. Raw builder graph

Owner layer:

- `builder`

Goal:

- implement the underlying mutable graph for instances and additive edges

Output artifact:

- raw builder graph type
- instance registry
- additive edge records

Verification target:

- focused raw-builder tests

Exit rules:

- instances can be added by name
- additive edges can be registered
- graph state is inspectable
- focused tests pass

### 4b. Root-instance-first handles

Owner layer:

- `builder`

Goal:

- expose builder, instance, and target handles with root-instance-first
  addressing

Output artifact:

- builder handle
- instance handle
- target handle

Verification target:

- focused handle/addressing tests

Exit rules:

- `builder.A` works
- `builder.A.first[0]` addressing shape is supported at the API level even if
  loop expansion is not yet implemented
- handle objects are stable and inspectable
- focused tests pass

### 4c. Fluent API and ordering validation

Owner layer:

- `builder`

Goal:

- wrap the raw graph with fluent additive operations and ordering rules

Output artifact:

- fluent builder operations
- equal-order conflict checks

Verification target:

- focused fluent-builder tests

Exit rules:

- fluent additive operations work
- equal-order conflicts fail
- fluent and raw APIs produce equivalent graph state
- focused tests pass

## 7. Milestone 5: Build, materialize, and loop expansion

Owner layer:

- `materialize`

Milestone goal:

- merge a builder graph into a new `Composable`
- keep unresolved boundaries open after build
- unroll supported compile-time loops
- materialize a valid runnable/emittable artifact

Milestone 5 exit gate:

- `build()` returns a merged `Composable`
- unresolved boundaries remain open after build
- non-unrolled loops remain loops
- supported loops unroll correctly
- materialize rejects incomplete/incompatible inputs
- end-to-end additive composition works
- focused materialize tests pass
- full test suite passes

### 5a. `build()` merge

Owner layer:

- `materialize`

Goal:

- merge builder graph state into a new composable while keeping unresolved
  boundaries open

Output artifact:

- `build()` implementation returning a merged `Composable`

Verification target:

- focused build tests

Exit rules:

- `build()` returns a `Composable`
- unresolved holes/loops/demands remain when not discharged
- focused tests pass

### 5b. Loop expansion

Owner layer:

- `materialize`

Goal:

- support unrolling of V1 compile-time loop domains and loop-expanded
  addressing

Output artifact:

- unroll logic for:
  - literals
  - constant `range(...)`
  - compile-time externals
- loop-expanded addressing support

Verification target:

- focused loop-unroll tests

Exit rules:

- supported domains unroll correctly
- non-unrolled loops remain in the resulting `Composable`
- loop-expanded addresses become available where applicable
- focused tests pass

### 5c. `materialize()` hard gate

Owner layer:

- `materialize`

Goal:

- produce a runnable/emittable artifact and enforce final compatibility and
  hygiene

Output artifact:

- `materialize()` implementation

Verification target:

- focused materialize tests
- end-to-end composition tests

Exit rules:

- mandatory unresolved holes fail
- incompatible composition fails
- accepted compositions produce a valid artifact
- focused tests pass

## 8. Milestone 6: Emit and provenance

Owner layer:

- `emit`

Milestone goal:

- emit source
- emit optional provenance payload
- restore provenance only when source AST shape still matches

Milestone 6 exit gate:

- `emit(provenance=True|False)` works
- provenance payload is appended only when enabled
- payload is AST/provenance restoration only
- edited/non-matching source hard-fails with the required error
- focused emit/provenance tests pass
- full test suite passes

### 6a. Source emission

Owner layer:

- `emit`

Goal:

- emit plain source from a composable/materialized artifact

Output artifact:

- source emission implementation

Verification target:

- focused source-emission tests

Exit rules:

- plain source emission works
- emitted source is valid Python for covered cases
- focused tests pass

### 6b. Provenance payload emission

Owner layer:

- `emit`

Goal:

- append compressed provenance payload when enabled

Output artifact:

- `astichi_provenance_payload("...")` emission

Verification target:

- focused provenance-emission tests

Exit rules:

- `provenance=True` appends the payload
- `provenance=False` omits the payload
- payload contains AST/provenance restoration data only
- focused tests pass

### 6c. Round-trip guardian

Owner layer:

- `emit`

Goal:

- validate payload/source AST shape match on subsequent reads

Output artifact:

- restoration/guardian check implementation

Verification target:

- focused round-trip tests

Exit rules:

- matching AST shape restores provenance
- edited/non-matching AST shape raises the required error
- error instructs removal of `astichi_provenance_payload("...")`
- focused tests pass
