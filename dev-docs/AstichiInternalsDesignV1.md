# Astichi internals design V1

This document defines the intended internal subsystem structure for Astichi V1.

It is not the public API specification. It is the internal design map that the
implementation plan should follow.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md`
- `astichi/dev-docs/AstichiImplementationBoundaries.md`
- `astichi/dev-docs/AstichiV1Milestones.md`

## 1. Goals

The Astichi implementation should be split into a small number of explicit
sub-libraries/modules with clear ownership.

The goals are:

- keep implementation layered
- avoid builder/materialize becoming one mud-ball
- keep hygiene isolated
- keep emitted-source/provenance logic separate from semantic lowering
- make milestone ownership obvious

## 2. Internal subsystem map

Astichi V1 should be organized around these internal subsystems:

- `asttools`
- `frontend`
- `lowering`
- `hygiene`
- `model`
- `builder`
- `materialize`
- `emit`

These names are directional. Exact file/module layout may vary slightly, but
the ownership boundaries should remain.

## 3. Subsystem definitions

### 3.1 `asttools`

Purpose:

- low-level AST helper library

Owns:

- AST shape helpers
- node cloning/copying helpers
- source-location/span helpers
- utility walkers/visitors/transformer helpers
- simple AST-context classification helpers

Must remain:

- small
- boring
- reusable
- semantics-light

Must not own:

- marker semantics
- builder semantics
- provenance policy
- public API semantics

Examples of likely contents:

- helper to identify starred/double-starred contexts
- helper to copy/fix locations
- helper to compare AST structural shape

### 3.2 `frontend`

Purpose:

- source entry and parse frontend

Owns:

- `astichi.compile(...)` entrypoint
- Python source parsing
- compile-origin metadata intake
- initial parse-time validation
- source reparse for emitted-source round-trips

Outputs:

- parsed AST
- source-origin context

Must not own:

- builder graph
- materialization
- source emission

### 3.3 `lowering`

Purpose:

- marker recognition and marker-lowering bridge

Owns:

- recognition of Astichi markers
- extraction of marker metadata
- recognition of identifier-only definitional binding sites
- shape inference from AST context
- lowered marker records/IR
- source-surface to internal-structure bridge

Outputs:

- marker-bearing lowered AST or equivalent structure
- marker records suitable for hygiene and model construction

Must not own:

- final hygiene resolution
- builder graph
- source emission

This is the first internal semantic currency layer.

### 3.4 `hygiene`

Purpose:

- lexical name classification and scope hygiene

Owns:

- scope objects / scope identity
- name classification
- explicit keep handling
- explicit external handling
- implied-demand handling
- hygienic renaming
- lexical collision checks

Outputs:

- hygienically valid lowered structure
- classification metadata

Must not own:

- builder addressing
- source emission
- provenance payload generation

This subsystem should be intentionally isolated because it will become subtle.

### 3.5 `model`

Purpose:

- immutable semantic carrier layer

Owns:

- `Composable`
- demand ports
- supply ports
- compatibility metadata
- target descriptors and similar immutable semantic structures

Outputs:

- valid immutable `Composable` instances
- explicit inspectable port structures

Must not own:

- mutable builder graph logic
- source emission
- provenance restoration

### 3.6 `builder`

Purpose:

- mutable composition graph and addressing

Owns:

- instance registry
- root-instance-first addressing
- loop-expanded target addressing when available
- additive edges
- ordering state
- fluent handles
- raw/assembler builder API

Outputs:

- mutable builder graph
- stable handles
- additive composition edges

Must not own:

- AST rewriting/materialization logic
- source emission
- provenance restoration

This subsystem should manipulate semantic graph structures, not directly
perform output-tree rewriting.

### 3.7 `materialize`

Purpose:

- build/materialization execution engine

Owns:

- `build()` merge behavior
- unresolved-boundary preservation
- compile-time loop unrolling
- final compatibility enforcement
- final hygiene closure
- final AST assembly for runnable/emittable output

Outputs:

- built `Composable`
- materialized AST or equivalent executable/emittable artifact

Must not own:

- source parsing frontend concerns
- provenance payload format

This is the execution core, but it must not absorb unrelated subsystems.

### 3.8 `emit`

Purpose:

- source emission and provenance payload handling

Owns:

- `emit(provenance=True|False)`
- source text generation
- `astichi_provenance_payload("...")`
- provenance restoration checks
- source-authority handling for emitted source

Outputs:

- source text
- optional provenance payload

Must not own:

- marker semantics
- builder graph semantics
- hidden semantic state transport

Marker semantics must always be rediscovered by reparsing source.

## 4. Dependency direction

Intended dependency direction:

- `asttools` <- reusable helper layer
- `frontend` -> `asttools`
- `lowering` -> `asttools`, `frontend`
- `hygiene` -> `asttools`, `lowering`
- `model` -> `lowering`, `hygiene`
- `builder` -> `model`
- `materialize` -> `asttools`, `model`, `builder`, `hygiene`
- `emit` -> `asttools`, `materialize`, `frontend`

The important rule is:

- later execution layers may depend on earlier ones
- earlier layers must not depend on later ones

## 5. Mapping to milestones

Milestone ownership should follow this mapping:

- Milestone 1 -> `frontend`, `lowering`, `asttools`
- Milestone 2 -> `hygiene`
- Milestone 3 -> `model`
- Milestone 4 -> `builder`
- Milestone 5 -> `materialize`
- Milestone 6 -> `emit`

This is the intended trunk of implementation.

## 6. Initial concrete module shape

An initial practical package layout could look like:

```text
src/astichi/
    __init__.py
    asttools/
    frontend/
    lowering/
    hygiene/
    model/
    builder/
    materialize/
    emit/
```

Or, if flatter modules are temporarily clearer:

```text
src/astichi/
    __init__.py
    asttools.py
    frontend.py
    lowering.py
    hygiene.py
    model.py
    builder.py
    materialize.py
    emit.py
```

Either is acceptable at phase start.

The important thing is the ownership boundary, not whether the first commit
uses packages or single modules.

## 7. Phase-1 simplifications

The following simplifications are deliberate:

- keep `asttools` shallow
- keep builder semantics additive-first
- keep `emit` from carrying hidden semantic state
- keep deep descendant traversal unresolved
- keep replacement semantics out of V1 internals

## 8. Warning signs

The implementation is drifting if:

- `builder` starts rewriting AST directly
- `emit` needs hidden semantic state that source reparse cannot recover
- `hygiene` is embedded ad hoc in unrelated modules
- `frontend` starts depending on builder/materialize details
- `materialize` becomes the default home for all unresolved design decisions

If one of these appears, stop and fix the boundary before proceeding.
