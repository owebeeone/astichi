# Astichi Assembler Concept

Status: active concept context.

This document records the current concept for an Astichi assembler layer for
clients such as YIDL. It is not an implementation plan yet. The goal is to keep
the data model, client contract, and ownership boundary explicit before adding
public API.

The immediate forcing case is recorded in
`scratch/YidlRequirementsForCodeGraphSynthesis.md`: YIDL needs to turn concept
facts, collections, matcher results, and scoped code treatments into a graph of
Astichi composables that can be validated and materialized.

## 1. Core Position

The assembler should be a tree-planning layer, not a recursive convenience
wrapper around the existing builder.

It should have two distinct phases:

1. Expansion: a client such as YIDL answers demands from collections, matchers,
   and semantic facts, then emits planned scope-tree contributions.
2. Execution: Astichi consumes the closed plan, validates composable
   descriptors, builds the scope tree from leaves to root, and materializes the
   requested artifact.

This split matches Astichi's existing boundary:

- the client owns semantic selection
- Astichi owns composable shape, descriptor validation, graph wiring, and final
  materialization

The assembler is viable because similar graph systems use the same separation:

- Bazel separates extension/rule analysis from action execution and uses
  providers to move structured information between targets.
  See <https://bazel.build/versions/9.0.0/extending/rules>.
- Terraform builds a dependency graph before walking it for plan/apply
  operations.
  See <https://developer.hashicorp.com/terraform/internals/graph>.
- Kedro modular pipelines use isolated reusable subgraphs with explicit
  inputs, outputs, and namespace-like adaptation.
  See <https://docs.kedro.org/en/0.19.5/nodes_and_pipelines/modular_pipelines.html>.
- Dask delayed records lazy tasks into a graph before execution.
  See <https://docs.dask.org/en/latest/delayed-api.html>.

The lesson for Astichi is not to copy any one system. The lesson is that a
client-specific semantic layer should emit concrete plan data, and the assembly
engine should validate and execute that plan deterministically.

## 2. Design Stance

Astichi should not learn YIDL concepts.

Astichi should not know about lifecycle fields, facades, transactions,
decorators, class-property semantics, or compiler-compiler rules. YIDL should
lower those ideas into generic assembly concepts:

- scopes
- target requests
- contributions
- edge overlays
- identifier bindings
- diagnostics context

Astichi should own:

- builder scopes as explicit isolated contexts
- immutable composable registration and reuse
- `Composable.describe()` as the structural source of truth
- target-address resolution
- compatibility checks
- per-scope build execution
- post-order scope-tree materialization
- deterministic build execution
- materialization and commented emission

The client should own:

- collection contents
- matcher evaluation
- semantic treatment selection
- target expansion
- binding-value computation
- requested artifacts
- user-facing diagnostic context

## 3. The Important Shape

The central data object should be an `AssemblyPlan` that owns the expanded
scope tree.

The plan should be callback-free after expansion. Once the client has answered
its demands, the plan should contain plain data that Astichi can inspect,
validate, walk, and execute without calling back into YIDL.

The expansion side may remain client-driven and lazy. The execution side should
be closed and deterministic.

This resolves the root/leaf tension in YIDL:

- demands begin at the requested root artifact
- child scopes are built from leaves to root once the scope tree is closed

Scopes are tree nodes in the current design. A source-level construct has one
logical source parent and one AST parent after generation. Reusing the same
template in multiple places means making multiple AST copies, not sharing a
scope result across parents.

Real generated-source sharing is expressed through identifiers:

- hoist one provider definition into a lexical ancestor
- export or otherwise expose a symbol from that provider
- satisfy child identifier demands by binding to that symbol

Cross-artifact sharing is an artifact/import concern. Build-time reuse of
rendered scope results may become an optimization later, but it must still
produce copied AST under each insertion parent and must not change source-level
semantics.

## 4. Assembly Algorithm

The assembler should own the mutable plan accumulator. Expansion methods should
not thread an explicit `plan` argument through every call.

The high-level algorithm is:

1. Start from the root `ScopeNode` for the requested artifact.
2. Create one root scope from that node and its root assembly context.
3. For each producer list in a scope, ask the list for producer nodes visible
   in the scope context.
4. For each `ProducerNode`, ask the client-side producer list for zero or more
   explicit selections.
5. Treat each selection as either a composable source selection or a child
   scope selection, and resolve that selection's target selector against the
   scope root description.
6. For source contributions, validate the selected source against the resolved
   target and resolve external binds plus identifier demands from the current
   assembly context.
7. For child-scope contributions, create and expand the child scope before
   treating that child result as a selected source in the parent scope.
8. Store every selected placement on the owning scope in the `AssemblyPlan`.
9. When expansion closes, validate the whole plan, build scopes in post-order,
   and materialize only the requested final artifact.

`AssemblyPlan` records the selected scope tree for the whole artifact. It does
not map sources to scopes separately. A source is used in a scope only when a
`Contribution` is stored on that scope.

External binds and identifier demands are resolved from the selected
composable's descriptor. Resolution is demand-driven; the client context
decides whether a client value is a literal value, generated code value,
runtime parameter, identifier spelling, or identifier supply.

Build execution converts each resolved scope into the L1 `ScopeBuildSet` shape
and lowers it through the current Astichi builder.

The algorithm's key invariants are:

- client context creates scopes and selects treatments
- descriptors validate the selected source against the target
- external binds are value/code/runtime-parameter resolutions
- identifier demands are symbol resolutions
- child scopes are expanded before the plan is closed
- build order is the post-order traversal of the scope tree
- L1 lowering receives only selected sources for one scope

## 5. Core Concepts

The authoritative API shape lives in `src/astichi/assembler`. This section
records the conceptual responsibilities behind those source contracts rather
than duplicating method signatures.

The client-owned core contracts are opaque, but not marker interfaces. Astichi
needs a small amount of stable behavior from each one for diagnostics, binding
lowering, and source selection.

`ScopeNode` and `ProducerNode` are distinct roles. A scope node creates a scope.
A producer node is input data consumed by a producer list. A concrete client
object may implement both roles when that is genuinely useful, but the
assembler API should not blur them.

`BindingValue.expression()` is where the client classifies identifier-like
data versus literal value data. For example, YIDL can lower `name` to
`ast.Name(...)` when it means an identifier reference, and to
`ast.Constant(...)` when it is a runtime string value such as a `setattr`
argument. Values that cannot or should not be inlined can lower to a named
runtime parameter expression owned by the generated builder function.

`ComposableSource` is not a core marker. It is a client-side source contract
only. It does not decide placement. `SourceSelection` and `ScopeSelection`
carry the target selector for the placement selected by the client.

The source does not provide `describe()`. Astichi obtains descriptor data from
`source.composable().describe()` so there is one structural source of truth.

### 5.1 Scope Plan

A scope plan is one node in the expanded scope tree. Its identity is the scope
object itself, not a semantic key.

Diagnostic names such as `Module`, `FacadeClass(public)`, or
`GetterEntry(count)` are derived from the scope node/context and parent chain.
They are not used for core wiring.

### 5.2 Scope Source

A source selected by expansion is either a concrete composable source or the
result of building a child scope.

The important point is that placement semantics live on the contribution, not
on the source itself. A selected composable source does not decide where it is
used. A contribution decides that by pairing the source with a target in the
scope that owns the contribution.

### 5.3 Scope Definition

A scope definition is the client-provided data needed to create one scope plan.

V1 should strongly prefer exactly one root composable per scope. Multiple
top-level roots can be supported later if there is a real use case, but one
root keeps scope-result identity clear.

### 5.4 Target Request

A target request is an unanswered demand for contributions.

In prose, the request says to fill a target in the current scope using a
client-owned collection and context. Astichi does not evaluate the collection.
The client expands the request into zero or more contributions.

### 5.5 Target Selector

A target selector identifies where a source should be placed.

V1 should support at least:

- a root-level hole by name
- a contribution-owned hole by name
- an exact descriptor-derived target address

The selector should be descriptor-resolved by Astichi. If a selector names a
hole that does not exist or names an ambiguous hole, the error should include
the request and contribution diagnostics supplied by the client.

### 5.6 Contribution

A contribution is one planned placement of one source into one target.

One client producer or matcher result may emit:

- no contributions
- one contribution
- many contributions targeting one or more holes in the owning scope

This is essential for matcher-driven generation. A treatment may select "no
code", one generated property, facade-specific output, or several placements of
the same reusable template. Each placement produces its own AST copy.

### 5.7 Edge Overlay

An edge overlay carries binding data that specializes a source at one
placement.

This mirrors existing builder edge overlays. The overlay belongs to the edge,
not to the reusable source resource.

### 5.8 Diagnostics Context

Every request and contribution should carry client diagnostic context.

Astichi should not interpret this context semantically, but should preserve it
in errors. YIDL needs failures to name the producer, matcher, rule, input
records, selected source, scope diagnostic path, and target hole when
available.

## 6. Client Contract

A client needs to provide these capabilities to the expansion phase.

### 6.1 Artifact Selection

The client declares which artifacts are requested.

Only requested artifacts should create root scope trees.

### 6.2 Scope Resolution

Given a scope node and parent context, the client resolves a
`ScopeDefinition`.

The scope definition must provide:

- root source
- root instance name
- producer lists
- diagnostics label

### 6.3 Source Selection

Given a producer node and assembly context, the client selects zero or more
contribution sources.

The source may come from:

- an Astichi code snippet
- an imported reusable composable
- a literal generated value that lowers to a composable
- a matcher-selected treatment
- a newly created child scope, represented first as a scope selection and later
  as a built `ChildScopeResult`

The selected source does not imply placement. The contribution that owns the
source decides where it is inserted inside its scope by carrying a target
selector.

### 6.4 Target Request Expansion

Given a `TargetRequest`, the client returns zero or more contributions.

This is where YIDL collections and matchers run. Astichi should not know why a
particular resource was selected.

The returned contribution data must be explicit:

- source reference
- target selector
- deterministic iteration position
- edge overlay
- identifier bindings
- diagnostics context

### 6.5 Binding Values

The client computes binding material from its current producer context.
Astichi must not decide whether a value is an identifier reference, a literal,
or a runtime parameter. The client returns a `BindingValue` that can lower to a
Python expression for the external bind site.

Astichi validates that the chosen source has matching external bind demands,
identifier demands, or other descriptor-visible requirements.

### 6.6 Ordering

Producer lists should return nodes in deterministic semantic order, and
producer output tuples should preserve any deterministic sub-order for one
producer node. Astichi can lower that iteration position to builder `order`
integers when it creates placements.

The client should not need a separate ordering callback unless a future case
needs to decouple traversal order from placement order.

## 7. Astichi Responsibilities

Once expansion produces a closed plan, Astichi should:

1. Resolve every scope root in the tree.
2. Resolve every selected target against `Composable.describe()`.
3. Reject missing or ambiguous targets with client diagnostics.
4. Check source/target compatibility.
5. Validate edge overlays against source demands.
6. Confirm every child scope is owned by exactly one parent path.
7. Build child scopes before parent scopes with post-order traversal.
8. Execute each scope through the existing builder graph.
9. Materialize or emit comments only at the final requested surface.

Astichi should not:

- evaluate YIDL matchers
- inspect client collection records
- infer YIDL semantic targets
- keep hidden semantic state in provenance
- receive unused candidate sources in the execution builder for a scope

## 8. Relationship To Existing Astichi Surfaces

The assembler should lower to existing builder mechanics wherever possible.

Likely correspondences:

- `ScopeDefinition.root` -> `builder.add("Root", root_composable)`
- selected source contributions -> named builder instances added only for
  that scope execution
- `Contribution` -> `builder.target(...).add(...)`
- `EdgeOverlay.bind` -> edge-local bind expression material, lowered to the
  builder binding mechanism
- `EdgeOverlay.arg_names` -> edge-local `arg_names=`
- `EdgeOverlay.keep_names` -> edge-local `keep_names=`
- identifier bindings -> descriptor-aware builder identifier binding
- final artifact -> `materialize().emit()` or `emit_commented()`

The existing raw builder graph remains valuable. The assembler should be a
higher-level plan compiler over that graph, not a replacement for it.

## 9. YIDL Getter Example

This is intentionally schematic.

YIDL starts with a root artifact request for a capsule module. The module
scope asks YIDL for contributions to the getter-entry target. For each field,
YIDL can choose whether to emit no code, emit a direct source contribution, or
emit a child scope contribution.

For a field getter child scope, the child scope owns the lower-level getter
value demand. A matcher in that child context chooses the concrete getter value
source and resolves field-specific binds such as the generated function name
and backing field name.

Execution builds the getter-entry child scope first, then inserts that child
scope result into the module scope.

## 10. V1 Recommendation

V1 should be deliberately conservative.

Required:

- `AssemblyPlan` data model
- one-root scopes
- selected sources carried by contributions
- child scope result references
- explicit target requests
- explicit contributions
- edge overlays
- descriptor target resolution
- descriptor compatibility validation
- post-order scope-tree build
- deterministic placement ordering

Deferred:

- final YIDL syntax
- automatic semantic target inference
- arbitrary Python callbacks inside a closed plan
- plan optimization or deduplication of identical rendered source
- parallel build execution
- multi-root scope results
- broad expression language for binding rules

The best first implementation path is to generalize the existing YIDL mapper
shape into data:

- turn template-edge plans into contributions
- turn child-port plans into target requests
- keep the existing named Astichi builder as the execution backend
- add descriptor preflight before materialization
- lower only selected sources into each scope's builder

## 11. Open Questions

1. Should target selectors be resolved immediately during expansion, or should
   resolution be deferred until the plan is closed?
2. How should a contribution target a top-level scope insertion instead of a
   named hole?
3. Is one root per scope sufficient for all near-term YIDL outputs?
4. What exact object should represent a contribution-owned target owner?
5. How much descriptor information should the client be able to query before
   emitting a contribution?
6. Should client diagnostic context be opaque, structured, or both?
7. Where is the public/private boundary between assembler API and raw builder
    graph API?

## 12. Design Risk

The largest risk is making the assembler too general too early.

The first useful version should solve the YIDL mapper problem with explicit
data. It should avoid becoming a generic rule engine, callback host, or
semantic compiler framework. Those belong in YIDL or other clients.

The second largest risk is allowing semantic decisions to leak into Astichi.
Once Astichi knows about YIDL-specific concepts, the boundary is lost. The
assembler should accept graph data from YIDL, not embed YIDL's reasons for
choosing that graph.

The third risk is skipping descriptor preflight. Without early structural
validation, large generated graphs will fail late during materialization with
errors that are technically correct but hard to connect back to the producer or
matcher that caused them.

## 13. Orthogonal Design Slices

The assembler concept should not be treated as one large implementation slice.
Several useful pieces can be designed as leaf libraries or leaf Astichi
features first.

For this purpose, a design slice counts as leaf-shaped when it:

- has a public or internal API that can be described without `AssemblyPlan`,
  `TargetRequest`, `Contribution`, or the expansion driver
- can be tested without a YIDL matcher or assembler expansion driver
- has standalone value for existing Astichi or YIDL code
- can later be called by the assembler without being redesigned around the
  assembler

This definition is stricter than "one phase of implementation." A slice that
only makes sense after the assembler exists is an implementation step, not a
leaf library.

### 13.1 L1: Scope Build Set Lowering

L1 is the per-scope lowering and execution slice.

It takes one already-expanded, selected scope build set and turns it into an
Astichi builder graph for that scope. It does not run matchers, expand
collections, walk the scope tree, or decide which sources are selected.

The input is the `ScopeBuildSet` shape defined in the assembler source. Its
sources are the named source composables available inside one scope, and its
placements are the additive edges into resolved targets.

The `target` should be descriptor-resolved before or during L1 lowering. The
preferred V1 contract is that L1 receives an exact target address, so L1 can
stay focused on builder execution rather than selector search.

L1 output is the built composable for exactly that scope.

The lowering operation is mechanical:

1. Create an Astichi builder.
2. Add the root as `root_instance`.
3. Add each selected source instance.
4. Add each placement edge to its resolved target.
5. Apply edge-local `bind`, `arg_names`, and `keep_names`.
6. Apply descriptor-aware identifier bindings when present.
7. Build and return the scope result composable.

L1 is leaf-shaped because it can be designed and tested with handcrafted
`ScopeBuildSet` values. It needs the builder and composable APIs, but it does
not need the assembler expansion driver, YIDL collections, matcher rules,
source registries, or scope-tree traversal.

Standalone payoff:

- gives Astichi a small explicit execution unit for one scope
- lets YIDL replace hard-coded recursive builder mutation with data lowering
- makes builder input precise enough to test before the full assembler exists
- keeps unused candidate sources outside the builder by construction

### 13.2 L2: Descriptor Query, Selector Resolution, And Compatibility

This is a strong leaf slice.

Astichi already has descriptor objects, but clients still need a clearer query
surface around them. This slice should provide a small API for structural
questions such as selector resolution, source/target compatibility, and
overlay validation.

The API should depend only on existing descriptor concepts such as
`ComposableDescription`, holes, productions, demand descriptors, and
`TargetAddress`.

The selector vocabulary can start small:

- hole by name
- hole by name plus ref-path disambiguation
- exact target address

The result vocabulary should be structured. It should not force clients to
parse exception text in order to decide whether a selector was missing,
ambiguous, incompatible, or invalid for the selected source.

This is leaf-shaped because it can be used directly by YIDL today, even before
an assembler exists. YIDL could preflight mapper decisions against real
Astichi descriptors, and existing Astichi users could write descriptor-driven
builder code with clearer diagnostics.

Standalone payoff:

- descriptor-driven clients can ask Astichi structural questions before
  mutating a builder
- the later assembler can delegate target resolution and compatibility checks
  to this library
- diagnostics become sharper without introducing assembler concepts

Risk: low to medium. The hard part is designing result/error objects that are
useful without turning into passive string tags. Per Astichi rules, semantic
results should be behavior-bearing objects rather than enums.

### 13.3 L3: Descriptor-Aware Identifier Binding

L3 is the descriptor-level identifier wiring slice.

It is already sketched separately in
`dev-docs/AstichiBindBuilderDesign.md`. The key API is a builder-level
operation that binds a descriptor-selected identifier demand to a
descriptor-selected identifier supply.

It requires:

- existing identifier demand/supply descriptors
- the builder graph
- materializer support for representing the direct scoped relationship before
  hygiene

Standalone payoff:

- descriptor-driven code can wire identifiers without unpacking descriptor
  fields into low-level assignment records
- Astichi gets a clearer public distinction between direct identifier binding
  and graph-qualified `assign(...)` aliasing
- the later assembler can lower planned identifier bindings through this API

Risk: medium. This slice touches scope and hygiene semantics more deeply than
descriptor query. It is still leaf-shaped, but it needs a sharper proof of
valid direct binding conditions.

### 13.4 Tree Walk And Shared Providers

Scope DAG scheduling is not part of the accepted V1 model.

The assembler builds scopes by post-order traversal of the scope tree. A child
scope has one logical parent. A generated AST subtree is inserted under one AST
parent. When the same template is needed in two places, the assembler creates
two placements and Astichi copies the AST as usual.

Shared generated-source behavior should be expressed through symbols, not
shared scope results:

- create one provider contribution in a lexical ancestor scope
- expose an identifier supply from that provider
- satisfy descendant identifier demands from that supply
- let final source contain one definition and many name references

This means there is no separate scope-DAG utility to design for V1.

### 13.5 Diagnostics Context Envelope

Diagnostics are a cross-cutting contract for the slices.

Every slice needs diagnostics, but the core idea is a convention:

- accept opaque or structured client context
- preserve that context through validation failures
- render it consistently near the structural Astichi error

That convention should be designed into L1, L2, and L3. It may become a small
shared error type later, but the first requirement is consistent propagation of
client context through structural Astichi errors.

### 13.6 Not Leaf-Shaped

The following concepts are important, but they are assembler vocabulary rather
than independent design slices:

- `AssemblyPlan`
- `ScopeDefinition`
- `TargetRequest`
- `Contribution`
- `ChildScopeResult`
- the expansion driver
- the client callback protocol
- scope-tree expansion and execution

These should be designed together because each one gains meaning from the
others. Pulling them apart would create premature APIs that either duplicate
the assembler or need redesign once the assembler exists.

### 13.7 Recommended Partition

The best independent design order is:

1. Scope build set lowering.
2. Descriptor query, selector resolution, and compatibility.
3. Descriptor-aware identifier binding, if direct identifier binding remains
   important before the assembler lands.

L1 and L2 are independent enough to design in parallel. L1 defines how one
resolved scope becomes a builder graph. L2 defines how target selectors and
source compatibility become resolved structural inputs. The assembler proper
then composes those leaves with expansion, source selection, provider-symbol
resolution, and tree execution.
