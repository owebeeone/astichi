# V1 deferred features

Tracking register for features and design directions surfaced in the historical
proposal (`dev-docs/historical/AstichiApiDesignProposal.md`) that are
intentionally out of scope for V1.

Each entry is kept to two lines maximum. Links to the originating section in
the proposal (§) are included where they apply.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md` (normative V1 design)
- `astichi/dev-docs/V1Plan.md` (V1 execution plan)
- `astichi/dev-docs/V1ProgressRegister.md` (authoritative progress tracker)
- `astichi/dev-docs/historical/AstichiApiDesignProposal.md` (source proposal)

## 1. Composable modeling

### 1.1 Effect tags (§2.1)

Port-side effects beyond `const`/`mutable` — read-only vs may-mutate, may-raise,
may-branch. V1 models only `mutability="const"` on ports.

### 1.2 Typed IO on ports (§2.2)

Type or kind summaries attached to demand/supply ports. V1 ports carry only
shape + placement + mutability.

## 2. Composition operations

### 2.1 Kernel `compose(a, b, pairing)` (§2.5)

Binary compose with an explicit edge-set argument. V1 uses an incremental
mutable builder graph as the raw surface instead.

### 2.2 `plug` ergonomic operator (§2.5)

One-edge-at-a-time compose sugar. V1 uses `target.add.Instance(order=N)`
fluent form.

### 2.3 `sequence` ergonomic operator (§2.5)

Convention-fixed pairing (e.g. two statement-list bodies). No V1 equivalent.

### 2.4 Batched compose (§2.5)

Many edges applied atomically in one call with a single scope/rename pass.
V1 resolves edges incrementally at `build()`.

### 2.5 Edge effect-ordering semantics (§3.4)

Edges that encode dataflow-vs-dominance-vs-both. V1 supports additive ordering
(`order=N`) on variadic holes only.

## 3. Emission

### 3.1 Marker-preserving (skeleton) source (§4)

Emit mode that keeps unsatisfied holes as visible sentinels for partial
programs. V1 emits plain Python or plain Python + pickled provenance comment.

### 3.2 Marker-grammar round-trip (§4)

"Emit-with-markers → parse → `Composable`" as a second pipeline. V1 round-trips
via the pickled-AST provenance payload only (`astichi/src/astichi/emit/api.py`).

### 3.3 `Source` / `Compiled` carrier types (§2.7)

Distinct carrier types for downstream pretty-print and code-object artifacts.
V1 returns a plain `str` from `emit()`.

### 3.4 Formatter policy / `__future__` / line tables (§2.7)

Formatter configuration, `__future__` handling, and line-table preservation
are explicitly outside the Composable closure in V1.

## 4. Binding and external values

### 4.1 `astichi_bind_external` value supply (§5.5)

The marker is recognized in V1, but there is no API for supplying compile-time
values that drive const-unroll, const insertion, or strategy evaluation.

### 4.2 `ComposeContext` (§5.3)

Ambient caller-supplied context carrying preserved names and external values.
V1 has no caller-supplied context; preserved-name logic is internal only.

## 5. Loops and unrolling

V1-lite loop unrolling is defined in `AstichiApiDesignV1-UnrollRevision.md`.
The items below remain deferred even after that revision.

### 5.1 External-domain loops (§3.6)

`astichi_for(items)` where `items` is supplied via `astichi_bind_external` or
caller context. V1-lite supports literals + `range(int_literal...)` only.

### 5.2 Runtime-iterable domains (§3.6)

Arbitrary runtime iterables as loop domains (lists from computation, generators,
etc.). Rejected at V1 unroll time.

### 5.3 Comprehension domains

Comprehension expressions used as loop domains, e.g. `astichi_for([x for x in
source])`. Rejected at V1 unroll time.

### 5.4 Arbitrary function-call domains

Function calls other than `range(...)`, e.g. `astichi_for(list(...))`,
`astichi_for(itertools.product(...))`. Rejected at V1 unroll time.

### 5.5 Constant folding of substituted bodies

Substituted literals are left as expressions (`arr[10] = 10 + 1`), not folded
(`arr[10] = 11`). Folding is a future optimization pass.

### 5.6 Loop variable shadowing as a supported pattern

V1 rejects same-scope rebind of a loop variable. Scope-aware substitution is
supported, but reintroducing the name in the same scope is not.

## 6. Addressing surface

### 6.1 Deep descendant traversal (§3.6)

Reaching into a sub-composable's sub-targets via chained paths. V1 locks first-
level root-instance addressing (`A.target`) + indexed (`A.target[i, j]`) only.

### 6.2 Cross-composable port navigation

Addressing a port on one composable through another composable's handle. Not
part of the V1 surface.

## 7. Open design areas (proposal TBD list)

### 7.1 Operator taxonomy

Formal catalog of composition operators beyond additive wiring (algebraic
properties, laws, expected equivalences). Not locked in V1.

### 7.2 Public scope-graph API (§2.7)

Exposing scope objects as a caller-visible surface rather than internal
machinery. V1 deliberately hides scope identity inside the hygiene layer.

### 7.3 Marker grammar specification

Formal grammar for marker-bearing Python (beyond the current structural marker
recognition). V1 has no formal grammar document.

### 7.4 Emission-vs-compile adapters (§2.7)

Pathways from `materialize()` into `exec`, `compile()`, or code-object carriers
as final morphisms. V1 stops at source text from `emit()`.

## 8. Composition surface

### 8.1 Replacement semantics (main design §5.8, §14)

Non-additive compose where a new contribution replaces an existing edge. V1 is
additive-only as an explicit phase-1 constraint.

### 8.2 Per-target materialization shapes (§3.2)

`materialize()` closing for a chosen shape (function, class, expression, module
fragment). V1 treats every composable as a module-level unit.

### 8.3 Optional-offer / dead-export tolerance policies (§3.2)

Policy for unwired optional supply ports at materialize. V1 does not model
"optional" as a first-class offer attribute.

## 9. Quality of life

### 9.1 Unified error-timing contract (§3.4)

A single documented contract for "errors at add vs build vs materialize." V1
picks error points per-feature; no unified contract is specified.

### 9.2 Diagnostics citing source origins

`CompileOrigin` is captured in V1 but most error messages do not yet cite
originating file/line information in their output.

## 10. Re-instatement policy

Any feature above may be re-instated by:

1. Drafting an addendum design document (`AstichiApiDesignV1-<Name>.md` or
   a new versioned design document) that resolves ambiguity and locks
   semantics.
2. Adding execution steps to `V1Plan.md` and `V1ProgressRegister.md` with
   exit criteria and verification targets.
3. Updating this document to move the feature from deferred to in-scope,
   preserving the original rationale in the commit history.

The loop-unrolling re-instatement (V1-lite, via
`AstichiApiDesignV1-UnrollRevision.md`) is the first application of this
policy and the template for future re-instatements.
