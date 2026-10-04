# Astichi API design V1: composition unification

This document locks the normative contracts around three properties that
the V1 base design and its addendums left partially specified:

- the **emit** contract (parseable, not executable);
- **idempotency** of the compose → build → emit → re-compile → build
  cycle (round-trip);
- **scoping** of every block insertion, whether authored in source via
  `@astichi_insert` or wired in the builder via `.add()`.

It also codifies the concrete consequence of these contracts: **every
block-level insertion produces an `astichi_insert` AST node in the
pre-materialize tree, regardless of whether the insertion was authored
in source or wired via the builder.**

This document supersedes the mode-based framing of
`AstichiApiDesignV1-MarkerPreservingEmit.md`; see §9 for the
relationship.

Related documents:

- `astichi/dev-docs/AstichiApiDesignV1.md` (base V1 design; §10–§12
  are the sections clarified here)
- `astichi/dev-docs/AstichiApiDesignV1-InsertExpression.md` (defines
  `astichi_insert` call/decorator surface; §§10–12 on scope boundary)
- `astichi/dev-docs/AstichiApiDesignV1-BindExternal.md` (bind is a
  separate transformation; unaffected)
- `astichi/dev-docs/AstichiApiDesignV1-UnrollRevision.md` (unroll
  operates on the pre-materialize `astichi_insert`-bearing tree)
- `astichi/dev-docs/AstichiApiDesignV1-MarkerPreservingEmit.md`
  (superseded; retained for historical rationale only)
- `astichi/dev-docs/IdentifierHygieneRequirements.md` (H1–H10 on
  hygiene; H5 on fresh scope at structural expansion)

## 1. Problem statement

The current implementation makes `.add()` and `@astichi_insert`
semantically different operations despite both performing "block goes
into hole":

- **`@astichi_insert(target)` in source** → recognized as a marker,
  treated by hygiene as a fresh Astichi scope boundary (per H5 and
  `InsertExpression.md §11`), collision-renamed.
- **`builder.Target.hole.add.Source()`** → splices the source's body
  directly at the hole position with no scope boundary and no marker
  residue in the output.

Two consequences follow:

1. **Silent name collision.** Two snippets independently defining a
   local `total = 0` both end up in the same Python scope after
   `.add()` wiring, silently overwriting each other. The hygiene
   engine does not see any scope boundary to rename across.
2. **Round-trip is lossy.** After `.add()`, the priority/ordering of
   contributions is baked into statement sequence and cannot be
   recovered from emitted source. Re-ingesting the emitted text and
   composing further produces a different composition graph — or no
   graph at all, because the holes are already gone.

Both flow from the same underlying cause: `.add()` drops the
information that the operation was an insertion. The only way to
preserve that information through emit/parse is to record it as an
AST node, and the incumbent node for that purpose is `astichi_insert`.

## 2. Contracts locked by this addendum

### 2.1 Emit contract

**`composable.emit(...)` produces parseable Python source. It does not
promise runtime executability.**

Specifically:

- The output is accepted by `ast.parse` and by `astichi.compile`.
- Any unresolved markers in the composable survive the emission —
  `astichi_hole(...)`, `astichi_bind_external(...)`,
  `astichi_insert(...)`, `astichi_for(...)`, `astichi_keep(...)`,
  `astichi_export(...)`, `astichi_definitional_name(...)`.
- Running the emitted module with `exec` / `compile(..., "exec")`
  will raise `NameError` on any surviving marker (none of them are
  real runtime functions). That is expected; it is not a bug.
- Hygiene closure is applied before unparsing, so the emitted text
  is internally consistent with the composable's scope structure.
- Provenance (per base §11.2) is embedded by default and round-trips.

The emit operation has **no `mode` parameter**. All emission is
parseable-first; the parseable-vs-executable axis is decided by
whether `materialize()` has run, not by an emit-mode toggle.

### 2.2 Materialize contract

**`composable.materialize()` closes a composable for runtime
execution.** A materialized composable satisfies three properties:

- Every mandatory demand port is resolved (holes, bind-externals)
  **and every `astichi_insert` supply points at an extant hole**.
  Any dangling insert — block shell or expression form — causes
  `materialize()` to raise at the gate (§2.5 (c)) before hygiene
  runs.
- Hygiene closure has been applied (fresh scope IDs assigned,
  collisions renamed), with the full complement of astichi markers
  still visible to the scope pass (§2.5 (b)).
- All `astichi_insert` contributions have been **flattened**: the
  decorator-wrapped shell functions are removed, their bodies are
  spliced at the hole position in topologically sorted order, and
  the originating `astichi_hole(...)` statement is removed. Other
  survived markers (`astichi_export`, `astichi_keep`,
  `astichi_definitional_name`) are stripped per §6.

`emit()` on a materialized composable therefore produces source that
is both parseable and directly executable.

A materialized composable is **terminal**: its emitted source no
longer contains the marker residue required to re-compose. Users who
want to emit-and-continue-composing must emit the pre-materialize
composable.

### 2.3 Idempotency contract (compose/build round-trip)

For any pre-materialize composable `c` produced by compile, build, or
bind:

```python
c1 = astichi.compile(c.emit())
# ast.dump(c1.tree) == ast.dump(c.tree)   # structural equality
```

This is the **round-trip invariant**. It holds for compose-build
cycles of arbitrary depth: emit → compile → build-more → emit → compile
→ … produces a consistent sequence of composables whose trees reflect
the accumulated composition.

Caveats:

- Hygiene-assigned synthetic identifiers (e.g. `total__astichi_scoped_1`)
  are part of the emitted source and are preserved by re-ingestion.
  They do not get renamed again on re-ingestion unless a new collision
  is introduced.
- Provenance payload, if emitted, is ignored during re-ingestion if
  the emitted source is the input to `astichi.compile`. The source is
  authoritative (base §12); the provenance is only a restoration aid.
- The invariant is `ast.dump` structural equality, not textual
  byte-equality. `ast.unparse` may choose slightly different textual
  forms for structurally identical trees.

For a **materialized** composable, the round-trip invariant is
weaker: `compile(materialized.emit())` produces a composable whose
demands are already empty and whose tree matches the flattened shape.
Re-composition against a materialized composable is not supported.

### 2.4 Scoping contract

**Every block-level insertion introduces a fresh Astichi-level scope
boundary.** This applies uniformly to:

- `@astichi_insert(target)` decorator-form authored in source;
- `astichi_insert(target, expr)` expression-form authored in source;
- `builder.Target.hole.add.Source()` insertions wired via the
  builder.

The scope boundary does not correspond to a Python scope in the
executable output — after materialize flattens the inserts, the
bodies live in the enclosing Python scope. The boundary exists
purely for hygiene's collision-rename pass: names introduced
(assigned) within one insertion are renamed if they collide with
names introduced within a sibling insertion, and free-name reads
resolve against the enclosing composable's scope.

Concretely, if two inserted bodies both write to a local `total`,
the hygiene engine renames them apart (e.g. `total` and
`total__astichi_scoped_1`). If an inserted body reads a name `x`
without assigning it, `x` resolves against the enclosing scope and
is not renamed.

This matches H5 (fresh scope on structural expansion) and the V1
rationale in `InsertExpression.md §11`.

### 2.5 Hygiene gate (hygiene runs only when all markers are in place)

Hygiene — the scope-identity + collision-rename pass — is owned
exclusively by `materialize()`. It runs **once**, and only when the
composable has reached a fully well-formed materializable state.
Two corollaries:

**(a) Hygiene runs nowhere else.** `compile()`, `build()`, `bind()`,
and `emit()` do not run hygiene. A pre-materialize composable carries
the original author-level names verbatim. This is what lets
compose → emit → re-compile → compose-more preserve the author's
intent (§2.3): hygiene has not yet committed to any name rewrites,
so the round-trip is a structural fixed point.

**(b) Hygiene sees every astichi marker still in the tree.**
Every marker — `astichi_hole`, `astichi_insert` (both block and
expression forms), `astichi_bind_external`, `astichi_keep`,
`astichi_export`, `astichi_definitional_name`, `astichi_for`, and
any future marker (`astichi_import`, `astichi_pass`, …) — is
present in the AST at the moment hygiene is invoked. Scope
computation is the single pass that owns scope decisions, and it
must have full visibility into authorial intent. A marker that
today looks like "just metadata" may carry scope semantics in a
future revision; pre-stripping any marker before hygiene would
silently remove information that a later revision might need to
consult. The only stripping permitted is the post-hygiene,
post-flatten residual strip (§6).

**(c) The materialize gate runs before hygiene and rejects any
composable that is not in its final well-formed shape.** The gate
refuses:

- any unresolved mandatory `astichi_hole(name)` (no matching
  `astichi_insert` in the same body);
- any unsupplied `astichi_bind_external(name)`;
- any **unmatched `@astichi_insert(name)` block shell** — a
  decorator-form insert whose target hole does not exist in the
  same structural body;
- any **unmatched expression-form `astichi_insert(name, ...)`** —
  i.e. a bare `ast.Expr` statement whose value is the insert call
  (an unwired expression supply declaration). The legitimate form
  after `build()` is an embedded wrapper at the former hole's
  expression position;
- (Phase 2) any `astichi_for(domain)` that the unroll pass could
  not fully resolve.

In other words: before hygiene runs, every insert must point at an
extant hole, and every hole and demand must be either satisfied or
explicitly optional. This is the "all markers in place" invariant.
If anything is out of place, materialize raises `ValueError` and
does not run hygiene — because running hygiene on a still-open
composable would commit to name rewrites before the authorial
intent was fully assembled.

**Rationale for strict rejection of unmatched inserts.** An
unmatched `@astichi_insert` shell is permissive: it silently grants
a fresh scope boundary to anonymous code with no consumer on the
other side. That pattern is exactly the kind of undocumented
affordance that a code-writing agent will latch onto — a "free
scope" sigil used to get isolation without declaring intent.
Rejecting it at the gate forces the author (human or AI) to declare
both the supply (the insert) and its consumer (the hole), which is
the structural contract the rest of the library relies on.

## 3. The unification rule

**At build time, `.add()` wiring produces `astichi_insert`-wrapped
contributions in the intermediate AST.**

Implementation shape: where `build_merge` currently splices a
source's body directly at a hole, it instead substitutes a list of
decorator-wrapped shells, one per contributing instance:

```python
# Before build_merge (Root):
astichi_hole(body)

# After build_merge (one contribution per .add()):
@astichi_insert(body, order=0)
def _Setup__contrib__():
    total = 0

@astichi_insert(body, order=1)
def _Step1__contrib__():
    total = total + 1

@astichi_insert(body, order=2)
def _Step2__contrib__():
    total = total + 2

astichi_hole(body)   # anchor preserved, see §3.1
```

The shell function name (`_Setup__contrib__` etc.) is generated from
the contributing instance name and an auto-incrementing counter for
disambiguation under repeated wiring. Shell function names are
hygiene-private (never used as a supply name or a reference target).

This pre-materialize form is the one that `emit()` textualizes. It
round-trips through `astichi.compile` cleanly because every
`astichi_insert(target, order=N)` is a valid Python call expression
and a recognized marker.

### 3.1 Hole anchor preservation

The originating `astichi_hole(name)` is **kept** in the
pre-materialize tree. Reasons:

- Round-trip: the hole's presence signals to a downstream composer
  "there is still a hole named `name` at this structural position."
  A composer may then wire additional contributions.
- Ordering anchor: newly-added contributions after a round trip can
  use `order=` values that are sorted against the already-present
  contributions; without the hole, the anchoring position is
  ambiguous.
- Symmetry with the source-authored form: if a user writes
  `astichi_hole(body)` followed by `@astichi_insert(body)` decorators
  in source, the tree already has the hole present alongside the
  inserts. `.add()` wiring now produces the same shape.

At materialize time, the hole and all satisfying inserts are
consumed together (per §4).

### 3.2 Order semantics

`astichi_insert(target, order=N)` has an explicit integer `order`
keyword as already defined by `InsertExpression.md §12`. Multiple
contributions to the same hole are sorted by `order` ascending;
equal-order contributions preserve authorial (or build-time)
sequence as a stable tie-break.

`.add()` wiring produces `order=` values sourced from the
`BuilderHandle.add(..., order=N)` argument. If the caller passes no
`order`, an auto-incrementing per-hole counter is used.

### 3.3 What `.add()` no longer does

`.add()` no longer performs body splicing. The actual splice — body
inlining at the hole position — is deferred to materialize's flatten
pass (§4). Before materialize, the tree carries the insert markers
verbatim.

## 4. Flatten pass in materialize

`materialize_composable` runs a strict, ordered pipeline. The key
invariant, restated: **the gate runs first, then hygiene on the
still-marker-bearing tree, then the flatten pass, and only then the
residual-marker strip.** Sequence:

1. **Gate.** Reject any composable that is not fully well-formed
   (§2.5): unresolved mandatory holes, unsupplied bind-externals,
   unmatched `@astichi_insert` block shells, unmatched
   expression-form `astichi_insert` calls, unresolved `astichi_for`
   loops. Gate failures raise `ValueError` and do not run any
   subsequent step.
2. Deep-copy the tree and recognize markers.
3. **Hygiene.** Assign scope identity; rename scope collisions. The
   tree at this point carries **every** astichi marker in its
   authorial position (§2.5 (b)). Scope boundaries therefore include
   decorator-wrapped `astichi_insert` shells, expression-form
   inserts, and any other markers that a future revision may treat
   as scope-relevant.
4. **Flatten `astichi_insert` contributions.** For each
   `astichi_hole(name)` with one or more satisfying `astichi_insert`
   contributions in the same body:
   - Sort the contributions by `order` ascending, stable.
   - Replace the hole-plus-contributions block with the concatenation
     of each contribution's body, in order. The decorator-wrapped
     shell function wrappers are removed; only the bodies survive.
   - The hole statement is removed.
5. **Strip residual markers** per §6 (`astichi_keep`, `astichi_export`,
   `astichi_definitional_name`). Stripping happens **after** hygiene
   and **after** flatten, never before.
6. Re-recognize markers and re-extract ports on the flattened,
   stripped tree. The resulting composable should have no demand
   ports and no `astichi_hole` / `astichi_insert` / residual markers.

The ordering is load-bearing:

- Gate before hygiene, so hygiene never runs on an incomplete
  composable.
- Hygiene before flatten, so collision-rename sees insert shells as
  scope boundaries; if rename ran after flattening, all boundaries
  would be lost and no renaming would happen.
- Flatten before strip, so the flatten pass can rely on hygiene-
  renamed names already being in place.
- Strip last, so hygiene had full marker visibility.

### 4.1 Flattening preserves order

The topological ordering of contributions (by `order=`, stable on
ties) is the one visible in the materialized tree. Two materializations
of structurally identical pre-materialize composables produce
identical flattened trees.

### 4.2 Flattening is non-reversible

A materialized composable cannot be round-tripped back to a
re-composable form. The flatten step discards the insert-marker
metadata irreversibly. Users who need both "executable source" and
"re-composable source" from the same composition keep a reference to
the pre-materialize composable.

## 5. Re-composition across round-trips

Given a pre-materialize composable `c` that has been emitted and
re-ingested:

```python
c.emit()         # contains astichi_insert(target, order=N) calls
# → astichi.compile(text) →
c2               # same structure; further .add() can append more
                 #   contributions to any hole
c2.build()       # may add more contributions, producing c3
c3.emit()        # contains c's inserts + c2's new inserts, ordered
c3.materialize() # flattens all in one pass
```

The `order=` values propagate through, so a downstream composer's
choice of `order=` is deterministic relative to the existing
contributions. This is the sense in which the cycle is idempotent:
absent new contributions, `compile(c.emit()).emit()` is structurally
equal to `c.emit()`.

## 6. Handling of residual markers at materialize

After the flatten step, the following markers may still appear in
the tree:

- `astichi_keep(name)` — user intent to protect a name from hygiene
  renaming. No longer needed at runtime. **Stripped.**
- `astichi_export(name)` — supply-port declaration. The port record
  survives on the composable; the marker statement is no longer
  needed at runtime. **Stripped.**
- `astichi_definitional_name(name)` — renaming directive applied
  during hygiene. Fully consumed by the rename pass. **Stripped.**
- `astichi_bind_external(name)` — if present on a materialized
  composable, the mandatory-demand gate in step 4 should already
  have rejected it. If a surviving marker reaches this point, it is
  a pipeline bug; raise an internal invariant error.
- `astichi_for(domain)` — if the unroll pass ran (V2 Phase 2), the
  loop has already been expanded and the marker is gone. If unroll
  did not run (e.g. `unroll=False`), the mandatory-demand gate
  should reject it as an unresolvable compile-time loop in the
  materialize context. Materialize does not retain `astichi_for`
  loops.

The residual-marker strip step is intentionally narrow: only markers
that are fully consumed by materialize are removed. Survived
`astichi_hole` or `astichi_insert` at this point indicates an
invariant violation, not a user error — the gate would have rejected
a missing hole, and the flatten step consumes matched inserts.

## 7. Scope-boundary mechanics

Implementation note, not user-visible contract.

The `_FreshScopeCollector` in `src/astichi/hygiene/api.py` (phase 4j
work) already recognizes the following as fresh Astichi scope
boundaries:

- `ast.FunctionDef`, `ast.AsyncFunctionDef` (native Python)
- `ast.ClassDef` (native Python)
- `ast.Lambda` (native Python)
- `ast.Call` matching `astichi_insert(...)` in expression position
  (phase 4j addendum)

For the unification to take effect, the collector must also recognize:

- `@astichi_insert(...)` decorators on a `FunctionDef` as a fresh
  scope boundary for the decorated function's body. This is already
  the case by virtue of the `FunctionDef` rule — the decorator itself
  is a marker but the body is inside the `FunctionDef` scope.

Because `.add()`-wiring produces decorator-form `astichi_insert` on
an auto-generated `FunctionDef` shell, the existing `FunctionDef`
boundary rule handles both source-authored and builder-wired inserts
uniformly. No new scope-collector rule is required.

## 8. Interaction with other V2 features

### 8.1 Bind (Phase 1)

`bind()` operates on the pre-materialize tree and substitutes
`Name(id, Load)` references. The tree at that time contains
`astichi_insert`-wrapped contributions. `bind()` descends into the
decorator-wrapped shell function bodies normally; the shell is a
standard `FunctionDef` to the bind visitor.

Scope boundaries for bind (per `BindExternal.md §7.3`) include
`FunctionDef`, so a parameter-shadowed name inside a shell halts
substitution naturally — but this case is unusual because the shell
functions generated by `.add()` are zero-argument by design.

### 8.2 Unroll (Phase 2)

Unroll operates on the pre-materialize tree. `astichi_for` loops
live in the enclosing scope (same as today). When an
`astichi_insert`-wrapped contribution contains an `astichi_for` loop,
the loop is unrolled inside the shell function body. The shell
itself is not duplicated; only the `astichi_for` loop body is.

No new interaction surface is required.

### 8.3 Marker-preserving emission

The `AstichiApiDesignV1-MarkerPreservingEmit.md` addendum is
superseded by this one: what it called `emit(mode="markers")` is
now the default behavior of `emit()` (parseable-first contract).
What it called `emit(mode="strict")` is now simply
`materialize().emit()`.

The existing document remains in `dev-docs/` as historical rationale
but its `mode=` API surface is not adopted.

## 9. Relationship to the MarkerPreservingEmit addendum

| MarkerPreservingEmit.md | This addendum |
|-------------------------|---------------|
| `emit(mode="strict")`   | `materialize().emit()` |
| `emit(mode="markers")`  | `emit()` (default) |
| `close_hygiene` factored out | Retained (still the right factor) |
| Skeleton textual fixed point | Round-trip invariant §2.3 |

`close_hygiene` is still the right internal factoring — it runs for
any emit path, whether the composable is materialized or not. The
`mode` parameter disappears because the distinction it encoded is
now carried by whether materialize has run, not by an emit argument.

## 10. Errors

### 10.1 At build time

- **No new errors.** `.add()` wiring produces `astichi_insert` nodes
  unconditionally; no user error is possible solely from the
  unification.

### 10.2 At materialize time

All of the following are raised by the **gate** (step 1 of §4),
before hygiene runs, as `ValueError`:

- **Unresolved mandatory hole** (existing): a `astichi_hole(name)`
  with no matching `astichi_insert(name, ...)` contributions in the
  same body. Raised with the hole's name and origin.
- **Unresolved bind-external** (existing, V2 Phase 1).
- **Unmatched `@astichi_insert` block shell** (new): a
  decorator-form insert on a `FunctionDef` whose target hole does
  not exist in the same structural body. Raised with the shell's
  target name and enclosing location.
- **Unmatched expression-form `astichi_insert`** (new): a bare
  `ast.Expr` statement whose value is an `astichi_insert(name, ...)`
  call — i.e. an unwired expression-form supply declaration.
  Wrapper shape is the legitimate post-build form: an
  `astichi_insert(name, expr)` call embedded in a non-statement
  expression position (inside an `ast.Assign` value, inside a
  call-argument list, inside an `ast.Starred`, as a dict entry,
  etc.). `build()` consumes every matched expression hole by
  substituting the wrapper at the hole's expression position, so
  a surviving bare-statement form at materialize time means no
  `build()` step consumed it and nothing will unwrap it.

Post-gate invariants (bugs, not user errors; surface as internal
errors):

- **Residual `astichi_hole` after flatten**: if the flatten step
  does not consume a hole that the gate accepted, the pipeline is
  broken.
- **Residual `astichi_insert` after flatten**: same as above.

### 10.3 At emit time

- **No new errors.** Emit is parseable-first; even an incomplete
  composable emits.

## 11. Implementation outline

1. **Modify `build_merge` in `src/astichi/materialize/api.py`** so
   that each hole-satisfying contribution produces an
   `astichi_insert`-decorated shell function rather than a direct
   body splice. The hole statement stays; the contribution shells
   are inserted immediately after (or before — pick a consistent
   position) the hole in the enclosing body.

2. **Add a flatten pass to `materialize_composable`** that runs
   after scope-identity/collision-rename and the demand gate, and
   before the final port re-extraction. The flatten pass:
   - groups `astichi_insert` contributions by target hole name;
   - sorts by `order` ascending (stable);
   - replaces the hole + satisfying shells with the concatenation
     of shell bodies at the hole's position.

3. **Add a residual-marker strip step** in materialize, per §6.

4. **Update `BasicComposable.emit()`** to drop any `mode=` parameter
   speculation. Emit takes `provenance=True|False` only, matching
   base §11.2.

5. **Update `AstichiApiDesignV1-MarkerPreservingEmit.md`** with a
   prominent superseded-by pointer at its top. Do not delete the
   file; it records the reasoning that led to this unification.

6. **Update `AstichiApiDesignV1.md §10–§11`** with the contract
   text from §2 of this document.

7. **Tests** (existing tests will break; that is the signal
   described in the code-yellow review):
   - **Round-trip invariant test** (new): `compile(c.emit()).tree`
     structurally equals `c.tree` for representative pre-materialize
     composables.
   - **Insertion scoping test** (new, should already fail today):
     two `.add()`-wired contributions each writing a local name
     `total` produce a materialized tree with renamed-apart `total`s.
   - **Materialize-emit executable test** (new): `exec(compile(
     c.materialize().emit(), "<t>", "exec"))` runs cleanly for a
     composable with no residual markers.
   - **Existing tests**: update per the triage buckets documented
     in the code-yellow review (shared-free-name fixtures, exec-of-
     unmaterialized-emit, structural assertions on merged trees).

8. **V2Plan.md update**: the 3f entry is no longer "add `mode=`";
   it is "document the emit contract and add round-trip invariant
   tests." The deliverable is the contract enforcement and the
   invariant tests, not a new API surface.

## 12. Non-goals for this addendum

- **No new emission mode.** Emit is parameterless beyond
  `provenance=`.
- **No new marker.** `astichi_insert` is the existing marker; this
  addendum only unifies its production sites.
- **No new user-visible error paths.** Errors all route through
  the existing demand-gate and hygiene-closure machinery.
- **No runtime representation change.** `BasicComposable` fields
  are unchanged.
- **No changes to bind or unroll user surface.** Their specs
  remain normative; this addendum only clarifies that the tree
  they operate on carries `astichi_insert` nodes for every
  insertion.

## 13. Deferred for future phases

- **Fine-grained order arithmetic.** `order=` is currently an
  integer; a future phase may introduce fractional or symbolic
  ordering tokens to support "insert between existing contributions
  X and Y." Not V2.
- **Anchorless inserts.** Currently every `astichi_insert` targets
  a named hole. A future phase may allow targeting a positional
  anchor in a body that was authored without an explicit hole. Not
  V2.
- **Partial-materialize.** A form of materialize that flattens some
  inserts but preserves others for downstream composition. Deferred
  to V2+.

## 14. Summary

The three contracts in §2 are the normative ones. Everything else in
this document is derivation or implementation direction.

- **Emit is parseable, not executable.** No mode parameter.
- **Compose-build cycles are idempotent** under round-trip through
  emit/compile.
- **Every insertion is a fresh Astichi scope.** `.add()` and
  `@astichi_insert` are unified around `astichi_insert` AST nodes.
