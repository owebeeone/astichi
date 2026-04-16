# V1 progress register

This document is the authoritative progress tracker for Astichi V1 execution.

Use it to identify the current goal, active layer, current milestone, next
action, and exit state.

## 1. Current status

- Overall status: not started
- Active milestone: none
- Active sub-phase: none
- Active implementation layer: none
- Current goal: establish the implementation plan and begin milestone 1
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
