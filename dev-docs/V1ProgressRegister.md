# V1 progress register

This document is the authoritative progress tracker for Astichi V1 execution.

Use it to identify the current goal, active layer, current milestone, next
action, and exit state.

## 1. Current status

- Overall status: in progress
- Active milestone: 1
- Active sub-phase: 1c
- Active implementation layer: asttools/lowering
- Current goal: complete milestone 1 AST-context shape inference
- Blockers: none recorded

## 2. Milestone register

### Milestone 1: Lowering pipeline

- Status: pending
- Owner layer: compile/lowering
- Goal:
  - parse source into Python AST
  - recognize V1 markers
  - capture compile origin metadata
  - infer marker shape from AST context
- Exit criteria:
  - `astichi.compile(...)` skeleton exists
  - marker recognition is test-covered
  - origin metadata is captured
  - valid/invalid marker placement tests pass
- Notes: none

Steps:

- [x] `1a` Status: complete
  - Goal: compile entrypoint skeleton
  - Output artifact: real `astichi.compile(...)` wrapper with origin metadata
  - Verification: focused frontend tests
- [x] `1b` Status: complete
  - Goal: marker recognition
  - Output artifact: marker records for V1 markers
  - Verification: focused lowering tests
- [ ] `1c` Status: pending
  - Goal: AST-context shape inference
  - Output artifact: shape inference metadata/helpers
  - Verification: focused shape-inference tests

### Milestone 2: Name classification and hygiene

- Status: pending
- Owner layer: name classification/hygiene
- Goal:
  - classify identifiers
  - implement strict/permissive handling
  - implement hygienic renaming
- Exit criteria:
  - classification order is implemented
  - keep-name preservation works
  - collision handling is test-covered
  - hygiene tests pass
- Notes: none

Steps:

- [ ] `2a` Status: pending
  - Goal: classification pass
  - Output artifact: classification routine and records
  - Verification: focused classification tests
- [ ] `2b` Status: pending
  - Goal: strict vs permissive handling
  - Output artifact: mode-aware unresolved-name behavior
  - Verification: focused strict/permissive tests
- [ ] `2c` Status: pending
  - Goal: hygienic renaming
  - Output artifact: rename transformer or equivalent rewritten structure
  - Verification: focused hygiene tests

### Milestone 3: Ports and composable carrier

- Status: pending
- Owner layer: composable/ports
- Goal:
  - define immutable `Composable`
  - extract demand/supply ports
  - implement compatibility validation
- Exit criteria:
  - compiling a snippet yields a valid `Composable`
  - demand/supply ports are inspectable
  - incompatible pairings hard-fail
- Notes: none

Steps:

- [ ] `3a` Status: pending
  - Goal: demand and supply port structures
  - Output artifact: immutable port types/metadata
  - Verification: focused model tests
- [ ] `3b` Status: pending
  - Goal: port extraction
  - Output artifact: extracted demand/supply ports on compiled snippets
  - Verification: focused port-extraction tests
- [ ] `3c` Status: pending
  - Goal: compatibility validation and composable carrier
  - Output artifact: concrete `Composable` backing plus compatibility checks
  - Verification: focused compatibility/composable tests

### Milestone 4: Builder graph and additive wiring

- Status: pending
- Owner layer: builder/addressing
- Goal:
  - add named instances
  - implement root-instance-first handles
  - implement additive edges and order validation
  - expose fluent and raw APIs
- Exit criteria:
  - instance/target handles work
  - additive edges are inspectable
  - equal-order conflicts fail
  - fluent/raw equivalence is test-covered
- Notes: loop-expanded addressing is completed in milestone 5

Steps:

- [ ] `4a` Status: pending
  - Goal: raw builder graph
  - Output artifact: mutable graph, instance registry, additive edges
  - Verification: focused raw-builder tests
- [ ] `4b` Status: pending
  - Goal: root-instance-first handles
  - Output artifact: builder/instance/target handles
  - Verification: focused addressing tests
- [ ] `4c` Status: pending
  - Goal: fluent API and ordering validation
  - Output artifact: fluent additive API and order-conflict checks
  - Verification: focused builder API tests

### Milestone 5: Build, materialize, and loop expansion

- Status: pending
- Owner layer: build/materialize
- Goal:
  - merge a builder graph into a new `Composable`
  - keep unresolved boundaries open after build
  - unroll supported compile-time loops
  - materialize a valid runnable/emittable artifact
- Exit criteria:
  - `build()` returns a merged `Composable`
  - non-unrolled loops remain loops
  - supported loops unroll correctly
  - materialization rejects incomplete/incompatible inputs
  - end-to-end additive composition works
- Notes: none

Steps:

- [ ] `5a` Status: pending
  - Goal: `build()` merge
  - Output artifact: merged `Composable`
  - Verification: focused build tests
- [ ] `5b` Status: pending
  - Goal: loop expansion
  - Output artifact: unroll logic and loop-expanded addressing
  - Verification: focused loop-unroll tests
- [ ] `5c` Status: pending
  - Goal: `materialize()` hard gate
  - Output artifact: materialized runnable/emittable artifact
  - Verification: focused materialize tests and end-to-end integration tests

### Milestone 6: Emit and provenance

- Status: pending
- Owner layer: emit/provenance
- Goal:
  - emit source
  - emit optional provenance payload
  - restore provenance only when source AST shape still matches
- Exit criteria:
  - `emit(provenance=True|False)` works
  - provenance payload is appended only when enabled
  - payload is AST/provenance restoration only
  - edited/non-matching source hard-fails with the required error
- Notes: source remains authoritative

Steps:

- [ ] `6a` Status: pending
  - Goal: source emission
  - Output artifact: plain source emission
  - Verification: focused emit tests
- [ ] `6b` Status: pending
  - Goal: provenance payload emission
  - Output artifact: compressed `astichi_provenance_payload("...")`
  - Verification: focused provenance-emission tests
- [ ] `6c` Status: pending
  - Goal: round-trip guardian
  - Output artifact: AST-shape restoration guard
  - Verification: focused round-trip/provenance tests

## 3. Working log

Add dated entries here as work proceeds.

Template:

```text
YYYY-MM-DD
- milestone:
- sub-phase:
- completed:
- verified:
- next:
- blockers:
```

## 4. Next-action rule

The next action should always be derivable from this document.

If it is not obvious what the next action is:

- update this register before continuing
- do not continue with implementation on implicit assumptions
