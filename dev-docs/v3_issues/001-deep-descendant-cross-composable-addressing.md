# 001: Deep descendant / cross-composable addressing

Status: open
Priority: blocking
Filed: V3

## Summary

Astichi's current builder surface is intentionally root-instance-first:

- additive targets are addressed as `<Root>.<hole>[indices...]`
- identifier wiring is addressed as
  `builder.assign.<Src>.<inner>.to().<Dst>.<outer>`

That is enough for first-level composition, but it is not enough for true
recursive composition.

Once a stage builds `B_n`, the later stage can only address:

- holes published on `B_n` itself
- identifier demands/supplies published on `B_n` itself

It cannot address a named descendant *inside* `B_n`, nor can it source a name
from a named descendant *inside* `B_n`.

This breaks compositionality. A built composable becomes an opaque box too
early, and later stages lose the ability to wire into or out of meaningful
internal structure.

## Current limitation

Today the implemented model is:

- root-instance-first addressing only
- optional numeric `path` indexing for unrolled holes
- no deep descendant traversal
- no public reference chain beyond `<instance>.<name>`

Concretely, these are supported:

```python
builder.Root.body.add.Step(order=0)
builder.Root.slot[0].add.Step(order=0)
builder.assign.Step.total.to().Root.total
```

This is *not* supported:

```python
builder.assign.Outer.Inner.total.to().Root.Setup.total
builder.Root.Inner.body.add.Step(order=0)
builder.assign.Pipeline.Parse.Normalize.field.to().Schema.Customer.id
```

The missing surface is the general descendant/reference form:

```text
<add_name/ref>.<inner_add_name/ref>...<param_name>
```

That form was part of the intended direction, but it is not implemented in the
current builder graph or fluent handle system.

## Why this is blocking

Without descendant/reference addressing, composition stops scaling as soon as a
piece is built in stages.

### 1. Built composables become opaque too early

If `S1` builds `B1` from several nested pieces, then `S2` can only talk to
`B1`'s published top-level holes and ports. Any internal structure that should
still be wireable in `S2` is hidden.

### 2. Later-stage parameter passing is incomplete

A later stage may need to supply a parameter to a nested shell or nested export
inside a stage-built composable. With only `<instance>.<name>`, there is no way
to name that nested target precisely unless every intermediate composable
manually re-exports or rethreads the name.

That is not composition. That is hand-plumbed forwarding boilerplate.

### 3. Internal reuse forces wrapper churn

Today, if a nested child inside `B1` owns the real port of interest, users must
add wrapper-level forwarding surface just to expose it at `B1`'s top level.
This creates:

- unnecessary exported names
- unnecessary boundary markers
- unnecessary aliasing pressure
- extra tests for wrapper plumbing instead of the real logic

### 4. Testability is compromised

The V3 staged-composition tests need to exercise:

- deep nesting
- later-stage identifier binding
- later-stage value binding
- mixed import/pass/export graphs
- delayed unroll under stage-built parents

Without descendant/reference addressing, many of those tests either cannot be
written cleanly or must be distorted into top-level re-export scaffolding.

## Minimal reproducible problem shape

```text
S1:
  C1 -> Inner
  C2 -> Inner
  Inner -> Middle
  Middle -> Root
  => B1

S2:
  need to bind / wire `Inner.total`
  need to source `Inner.result`
  but only `B1.total` / `B1.result` are nameable
```

If `Inner.total` is not deliberately republished at every wrapper layer, stage 2
cannot express the desired connection.

That means recursive composition is not closed under `build()`.

## Required V3 capability

V3 needs a descendant/reference addressing model that can name ports
below the root instance boundary.

At minimum it must support:

1. descendant target addressing for additive composition
2. descendant source/target addressing for identifier wiring
3. stable semantics across stage-built composables
4. compatibility with unroll indexing

The user-facing idea is:

```text
<instance>.<descendant>...<hole>
<instance>.<descendant>...<param>
```

Where each hop names a descendant reference, not an implementation-only
AST node.

## Non-goals

This issue is **not** asking for:

- arbitrary AST-node traversal
- path syntax that depends on internal lowered names
- replacement semantics
- reflective access to unnamed implementation scaffolding

The goal is compositional descendant/reference addressing, not reflective
introspection over implementation details.

## Proposed direction

### 1. Add a descendant reference model

Each built composable must be able to preserve a descendant/reference
graph for named composition-relevant children.

That graph should be:

- explicit
- stable across `build()`
- separate from raw AST implementation details

### 2. Extend builder handles beyond root-instance-first

The current handle system stops at:

- `builder.<Instance>.<hole>`
- `builder.assign.<Instance>.<param>`

V3 should add a descendant/reference chain surface so users can express:

- nested target holes
- nested identifier demands
- nested identifier supplies

without forcing wrapper-level republishing.

### 3. Keep the model additive-first

Deep addressing must not weaken the current builder discipline:

- no replacement semantics
- no "best effort" optional offers
- no hidden traversal guesses

Every deep reference must still be explicit and name-based.

### 4. Distinguish addressable descendants from implementation internals

A built composable should not expose every nested AST detail. It should expose
named descendants by default as part of the
composable contract.

That may mean:

- explicit descendant metadata on the composable model
- explicit default-public descendant propagation during `build_merge`
- explicit rules excluding synthetic/internal scaffolding from the addressable
  surface

## Implementation scope

This issue is larger than a fluent-syntax tweak. The builder/model/materialize
layers all need changes.

## Scoped-down V3 model

To keep this landable as a one-shot feature, V3 should implement the smallest
useful descendant model:

- descendant addressing uses a mixed path of named segments and index segments
- every named descendant is addressable by default across `build()` boundaries
- descendant refs are instance-structure refs, not arbitrary AST refs
- ambiguous repeated-use cases reject instead of introducing aliasing or
  publication controls
- synthetic/internal scaffolding is never part of the address space

The intended path shape is:

```text
<root>.(<descendant_ref> | [i, ...])*.<leaf_name>
```

Examples:

```python
builder.Root.Parse.body.add.Step(order=0)
builder.Root.Parse.rows[1, 2].Normalize.body.add.Step(order=0)
builder.assign.Pipeline.Parse.rows[1, 2].field.to().Schema.Customer.id
```

This is the simplified rule set for the first implementation. Anything beyond
that should be treated as a follow-up issue, not folded into this one.

### 1. Surface and naming model

V3 needs a descendant/reference chain surface for both:

- additive target addressing
- identifier wiring

The intended shape is:

```text
<instance>.<descendant/ref>...<hole>
<instance>.<descendant/ref>...<param>
```

The key word is **ref**. In the scoped-down model, descendant refs are just the
named instance occurrences created by additive composition, composed with
existing unroll index segments.

So the implementation must define:

- what counts as a descendant reference
- how name segments and index segments interleave
- when a reused instance name becomes ambiguous and must reject

For a first implementation:

- treat descendant references as a distinct namespace that survives `build()`
- disallow ambiguity between a descendant reference and a hole/port name at the
  same level
- reject collisions rather than guessing
- reject ambiguous repeated-use descendants instead of adding aliases/refs

That is stricter, but it keeps the semantics legible while the feature lands.

### 2. Fluent handle changes

Current handles stop at:

- `builder.Root.body`
- `builder.assign.Step.total.to().Root.total`

V3 must extend:

- `InstanceHandle`
- target handles
- assign source/target pickers

so that the chain can continue through descendants before reaching the
final hole/param hop.

This means:

- `__getattr__` can no longer assume "the next hop from an instance is always a
  target"
- the assign chain can no longer assume "the next hop after `<Src>` is always
  the final inner name"

The handle layer therefore needs a descendant-aware intermediate object model,
not just a small patch to `TargetHandle`.

### 3. Builder graph changes

Current graph records only:

- `TargetRef(root_instance, target_name, path=(...))`
- `AssignBinding(source_instance, inner_name, target_instance, outer_name)`

That is insufficient for descendant/reference chains.

V3 needs the graph to store:

- descendant target paths
- descendant source paths
- descendant target-instance paths for assign bindings
- mixed descendant + unroll index paths

The likely shape is:

- path segments for named descendant refs
- numeric path segments for unroll indices

stored separately or as a tagged sequence, but not collapsed into a single
string.

For the scoped-down implementation, the named segments only need to represent
builder-instance descendant hops. Do not generalize this to arbitrary internal
named AST nodes.

### 4. Composable model changes

`BasicComposable` currently preserves:

- AST
- markers
- demand ports
- supply ports
- arg bindings
- keep names

It does **not** preserve a descendant/reference graph.

That graph must be added explicitly. Scanning the merged AST later is not
enough, because once `build_merge` flattens the stage:

- descendant ownership is lost
- multiple inserted occurrences are indistinguishable
- internal shell names are implementation scaffolding, not public contract

So V3 needs first-class descendant metadata on the composable model.

### 5. `build_merge` changes

`build_merge` is where stage boundaries currently collapse nested structure into
one merged tree.

V3 must teach it to:

- propagate descendant/reference metadata across merge
- prefix descendant paths through the current stage instance names / refs
- preserve enough identity that later stages can still name nested descendants
- carry descendant refs through root-wrap scaffolding without exposing the
  synthetic root wrappers as public names

This is the core implementation work.

### 6. Validation and diagnostics

V3 must add validation for:

- unknown descendant refs
- ambiguous refs
- hole-name vs descendant-ref collision
- param-name vs descendant-ref collision
- illegal mixed descendant/index paths
- references to unknown or synthetic/internal descendants

For the first implementation, collision rejection is preferable to any silent
precedence rule. Ambiguous repeated-use descendant paths should also reject
instead of acquiring ad hoc resolution rules.

### 7. Tests

The tests must cover:

- one-hop descendant target addressing
- multi-hop descendant target addressing
- one-hop descendant assign addressing
- multi-hop descendant assign addressing
- reused source instance with multiple named descendant refs
- descendant refs across stage boundaries
- descendant refs combined with unroll indices

## Likely first-implementation rule set

To keep the feature landable, the first implementation should likely enforce:

1. descendant refs are explicit names that survive stage closure by default
2. ambiguity is a hard error
3. no silent precedence between:
   - descendant ref
   - hole name
   - identifier demand/supply name
4. descendant refs are preserved in composable metadata, not rediscovered from
   emitted/internal names
5. unroll addressing is part of the core path model, not a later extension
6. reused source instances reject when they would create ambiguous descendant
   paths

## Known hazards

### 1. Source-instance reuse breaks naive name-based traversal

This is the biggest trap.

If one source instance is inserted into two places:

```text
Root.left  <- Step
Root.right <- Step
```

then `<instance>.Step` is not enough to identify one structural occurrence.

V3 should, for now:

- reject descendant addressing for multiply-used instances when the path would
  be ambiguous
- defer edge-local refs / aliasing to a later issue

Do not assume instance names alone solve this.

### 2. AST scanning is necessary but not sufficient

Port extraction already scans the tree widely enough to find markers and
identifier ports.

That does **not** solve descendant addressing.

Scanning the merged AST can tell us:

- what ports exist

but not:

- which descendant they belonged to before the stage collapsed
- which occurrence of a reused source instance they came from
- what descendant chain should name them

So "scan the whole AST for identifiers" is part of the implementation story,
but it does not remove the need for explicit descendant metadata.

### 3. `astichi_insert` names are not enough

`astichi_insert(name, ...)` and `astichi_hole(name)` already give us target
names.

That helps with the **hole** side of the path.

It does not solve:

- descendant reference identity
- multiply-inserted source instances
- source-side identifier naming

So no marker-surface change may be needed for hole naming, but that alone does
not land the feature.

### 4. Unroll path composition can get messy fast

Descendant paths and index paths must compose under one rule, e.g.:

```text
Pipeline.Parse.rows[0].Normalize.field
```

Do not bolt on a second indexing scheme or a stringly-typed path parser.

### 5. Root-wrap scaffolding must remain private

`build_merge` currently introduces synthetic root-wrap shells for scope
isolation. V3 must preserve descendant identity through that step without
publishing `__astichi_root__...` names as addressable refs.

### 6. Backward-compatibility pressure in `__getattr__`

Today a hop like `builder.A.slot` is always interpreted as a target name.

Once descendants exist, the same hop could mean:

- descendant ref
- target hole
- identifier port

If the fluent surface keeps plain chained attributes, ambiguity handling must be
designed before implementation, not patched afterwards.

## Open design questions

### 1. What is the naming primitive?

For the scoped-down implementation:

- chained attribute syntax plus existing `[...]` indexing
- no separate alias/reference declaration API in this issue
- no raw string path syntax in the public API

### 2. What survives a stage boundary?

For V3, the rule should be:

- every named descendant survives by default
- synthetic/internal scaffolding does not become addressable

The implementation should document that strictly and avoid adding a
public/private publication mechanism in this issue.

### 3. How does this interact with unroll?

Unroll is in scope for this issue. The rule is combinations like:

```text
<instance>.<descendant>.slot[0, 1]
```

Unroll indexing composes with descendant addressing under the same mixed path
model. No second path syntax should be introduced.

### 4. How does this interact with import/pass/export?

Identifier wiring currently assumes:

```text
<instance>.<inner> -> <instance>.<outer>
```

V3 needs the descendant form of that same contract, not a separate special API.

### 5. How much of this should be available before `materialize()`?

The answer affects:

- emitted marker-preserving round-trip
- composable metadata
- staged-build testability

## Suggested implementation constraints

- Do not encode descendant addressing as raw filesystem-like strings stored in
  random places.
- Do not couple it to lowered hygienic names.
- Do not make later-stage behavior depend on reparsing private emitted text to
  rediscover descendants.
- Preserve a plain raw API underneath the fluent surface.

## Tests needed

### Spine tests

- staged deep-order trace where stage 2 targets a descendant inside `B1`
- later-stage identifier wiring into a descendant inside a stage-built parent
- later-stage sourcing from a descendant export/pass inside a stage-built parent
- nested unroll plus descendant addressing in the same scenario

### Matrix tests

- root vs one-hop descendant vs two-hop descendant
- additive hole vs identifier demand vs identifier supply
- same-stage vs later-stage addressing
- identity rebind vs non-identity rebind
- unrolled index at the leaf vs no unroll

### Negative tests

- unknown descendant reference rejects clearly
- reference to an unknown or synthetic/internal descendant rejects clearly
- ambiguous repeated-use descendant path rejects clearly
- conflicting descendant bindings reject clearly
- malformed mixed descendant/index path rejects clearly

## Relationship to current V3 test plan

`dev-docs/AstichiV3TestPlan.md` currently models the implemented builder
surface, which stops at `<instance>.<name>`.

That is correct for testing the code that exists today, but it is not the
surface the long-term composition model needs.

This issue is therefore upstream of part of the V3 test plan:

- some staged-composition tests can be written now against the current surface
- the full deep-nesting composition story requires this issue to land

## Bottom line

Astichi is not compositionally complete while `build()` collapses nested
structure into an opaque top-level surface.

V3 must add descendant/reference addressing across stage-built composables.

Without that, recursive composition works only when every intermediate wrapper
manually republishes every nested thing that later stages might care about, and
that is precisely the kind of boilerplate Astichi is supposed to remove.
