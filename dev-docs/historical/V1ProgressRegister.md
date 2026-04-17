# V1 progress register

This document is the authoritative progress tracker for Astichi V1 execution.

Use it to identify the current goal, active layer, current milestone, next
action, and exit state.

## 1. Current status

- Overall status: in progress
- Active milestone: 7 (next planning)
- Active sub-phase: n/a
- Active implementation layer: n/a
- Current goal: milestones 5 and 6 complete; assess milestone 7+
- Blockers: none recorded

## 2. Milestone register

### Milestone 1: Lowering pipeline

- Status: complete
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
- [x] `1c` Status: complete
  - Goal: AST-context shape inference
  - Output artifact: shape inference metadata/helpers
  - Verification: focused shape-inference tests
- [x] `1d` Status: complete
  - Goal: identifier-only definitional site recognition
  - Output artifact: lowered records for supported class/function definitional names
  - Verification: focused definitional-name recognition tests

### Milestone 2: Name classification and hygiene

- Status: complete with follow-up
- Owner layer: name classification/hygiene
- Goal:
  - classify identifiers
  - implement strict/permissive handling
  - implement hygienic renaming
  - establish the phase-1 hygiene machinery
- Exit criteria:
  - classification order is implemented
  - keep-name preservation works
  - collision handling is test-covered
  - hygiene tests pass
- Notes: scope-collision completion is tracked separately as milestone-4 follow-up work

Steps:

- [x] `2a` Status: complete
  - Goal: classification pass
  - Output artifact: classification routine and records
  - Verification: focused classification tests
- [x] `2b` Status: complete
  - Goal: strict vs permissive handling
  - Output artifact: mode-aware unresolved-name behavior
  - Verification: focused strict/permissive tests
- [x] `2c` Status: complete with follow-up
  - Goal: hygienic renaming
  - Output artifact: rename transformer or equivalent rewritten structure
  - Verification: focused hygiene tests
  - Note: scope-collision completion is deferred to `4d`–`4f`

### Milestone 3: Ports and composable carrier

- Status: complete
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

- [x] `3a` Status: complete
  - Goal: demand and supply port structures
  - Output artifact: immutable port types/metadata
  - Verification: focused model tests
- [x] `3b` Status: complete
  - Goal: port extraction
  - Output artifact: extracted demand/supply ports on compiled snippets
  - Verification: focused port-extraction tests
- [x] `3c` Status: complete
  - Goal: compatibility validation and composable carrier
  - Output artifact: concrete `Composable` backing plus compatibility checks
  - Verification: focused compatibility/composable tests

### Milestone 4: Builder graph and additive wiring

- Status: complete
- Owner layer: builder/addressing, lowering/asttools (4g, 4h), model (4i),
  hygiene (4d–4f, 4j)
- Goal:
  - add named instances
  - implement root-instance-first handles
  - implement additive edges and order validation
  - expose fluent and raw APIs
  - complete the missing scope-collision hygiene work needed before build and
    materialize
  - extend `astichi_hole` shape inference to cover dict display `**` context
  - implement expression-form `astichi_insert` marker recognition
  - implement expression-insert supply port extraction
  - implement expression-insert scope boundaries per H5
- Exit criteria:
  - instance/target handles work
  - additive edges are inspectable
  - lower `order` comes before higher `order`
  - equal `order` on the same target preserves insertion order
  - fluent/raw equivalence is test-covered
  - `astichi_hole` in dict `**` context correctly infers `NAMED_VARIADIC`
  - expression-form `astichi_insert` is recognized with 2 positional args
  - expression inserts produce supply ports with placement `"expr"`
  - expression-insert sites are treated as H5 scope boundaries
- Notes:
  - loop-expanded addressing is completed in milestone 5
  - `4d`–`4f` are hygiene-owned follow-up work required before step 5
  - `4g`–`4j` implement expression-insert support per
    `AstichiApiDesignV1-InsertExpression.md` sections 10–12

Steps:

- [x] `4a` Status: complete
  - Goal: raw builder graph
  - Output artifact: mutable graph, instance registry, additive edges
  - Verification: focused raw-builder tests
- [x] `4b` Status: complete
  - Goal: root-instance-first handles
  - Output artifact: builder/instance/target handles
  - Verification: focused addressing tests
- [x] `4c` Status: complete
  - Goal: fluent API and ordering validation
  - Output artifact: fluent additive API and deterministic ordering behavior
  - Verification: focused builder API tests
- [x] `4d` Status: complete
  - Goal: scope object attachment and preservation
  - Output artifact: scope-identity model and preserved-name handling
  - Verification: focused scope-identity tests
- [x] `4e` Status: complete
  - Goal: structural expansion scope freshness
  - Output artifact: fresh-scope behavior for injected or expanded units
  - Verification: focused scope-freshness tests
- [x] `4f` Status: complete
  - Goal: scope-collision renaming
  - Output artifact: scope-aware collision renaming required by `IdentifierHygieneRequirements.md`
  - Verification: focused scope-collision tests
- [x] `4g` Status: complete
  - Goal: dict-context `astichi_hole` shape inference
  - Output artifact: updated `_infer_shape` detecting dict `**` context as
    `NAMED_VARIADIC`; explicit test coverage for dict key position as
    `SCALAR_EXPR`
  - Verification: focused dict-context shape tests
- [x] `4h` Status: complete
  - Goal: expression-form `astichi_insert` marker recognition
  - Output artifact: dual-context `astichi_insert` recognition (call: 2 args,
    decorator: 1 arg); expression-insert shape always `SCALAR_EXPR`
  - Verification: focused expression-insert marker tests
- [x] `4i` Status: complete
  - Goal: expression-insert supply port extraction
  - Output artifact: supply ports from expression inserts; updated placement
    compatibility (`"expr"` supply matches any `"expr"` demand sub-shape)
  - Verification: focused supply-port and compatibility tests
- [x] `4j` Status: complete
  - Goal: expression-insert scope boundaries
  - Output artifact: fresh H5 scope object per expression insert; internal
    bindings scoped to insert (H6); free names retain outer scope (H7)
  - Verification: focused expression-insert scope-boundary tests
  - Note: depends on 4d–4f scope machinery

### Milestone 5: Build and materialize

- Status: complete
- Owner layer: build/materialize
- Goal:
  - merge a builder graph into a new `Composable`
  - keep unresolved boundaries open after build
  - materialize a valid runnable/emittable artifact
- Exit criteria:
  - `build()` returns a merged `Composable`
  - `astichi_for` loops remain as-is (loop expansion deferred)
  - materialization applies final hygiene closure
  - materialization rejects incomplete/incompatible inputs
  - end-to-end additive composition works
- Notes: loop expansion (5b) deferred from V1; users manually wire multiple
  inserts for equivalent functionality

Steps:

- [x] `5a` Status: complete
  - Goal: `build()` merge
  - Output artifact: merged `Composable` via topological edge resolution
  - Verification: focused build tests (9 tests)
- [x] `5b` Status: deferred
  - Goal: loop expansion
  - Output artifact: deferred — `astichi_for` loops remain as-is
  - Verification: n/a
  - Note: deferred from V1; manual unrolling via multiple inserts is the
    workaround
- [x] `5c` Status: complete
  - Goal: `materialize()` hard gate
  - Output artifact: materialized artifact with hygiene closure applied
  - Verification: focused materialize tests (5 tests)

### Milestone 6: Emit and provenance

- Status: complete
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
- Notes: provenance format is pickle → zlib compress → base64 encode;
  embedded as a trailing `# astichi-provenance: ...` comment

Steps:

- [x] `6a` Status: complete
  - Goal: source emission
  - Output artifact: `emit_source()` via `ast.unparse` with trailing newline
  - Verification: focused emit tests (5 tests)
- [x] `6b` Status: complete
  - Goal: provenance payload emission
  - Output artifact: `encode_provenance` / `decode_provenance`
  - Verification: focused provenance-emission tests (5 tests)
- [x] `6c` Status: complete
  - Goal: round-trip guardian
  - Output artifact: `verify_round_trip()` with `RoundTripError`
  - Verification: focused round-trip tests (4 tests)

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
