# Astichi Builder Identifier Binding Design

Status: proposal.

## 1. Problem

The descriptor API exposes identifier wiring surfaces:

- `IdentifierDemandDescriptor`
- `IdentifierSupplyDescriptor`

These descriptors carry the data needed to wire a builder graph:

- the identifier name
- the descriptor port
- the descendant `ref_path` where the demand or supply lives

Today, descriptor-driven code must unpack those fields manually into
`builder.assign(...)`:

```python
builder.assign(
    source_instance="Consumer",
    source_ref_path=shared_demand.ref_path,
    inner_name=shared_demand.name,
    target_instance="Pipeline",
    target_ref_path=shared_supply.ref_path,
    outer_name=shared_supply.name,
)
```

That is correct but mechanical. It also makes descriptor-driven identifier
wiring look different from descriptor-driven additive wiring, where the builder
already accepts descriptor target data directly:

```python
builder.target(hole.with_root_instance("Pipeline")).add("Step")
```

The bigger problem is semantic, not just mechanical. A descriptor-selected
supply is a scope-aware identifier surface. Descriptor-driven identifier binding
should express that relationship in the pre-hygiene AST/shell structure instead
of forcing the long internal assign alias currently used for every
path-qualified `builder.assign(...)`.

The desired user-facing concept is:

> Bind this identifier demand to that descriptor-selected identifier supply.

The binding should be represented so the source identifiers and selected supply
participate in the normal Astichi scope/hygiene pipeline. Final spelling is
then chosen by the existing hygiene pass. If the relationship cannot be
represented as a valid scoped identifier binding, materialization should fail
with a clear diagnostic. Callers who want the existing fully qualified alias
behavior should keep using `builder.assign(...)`.

## 2. Recommendation

Add a builder-level descriptor-aware binding method:

```python
builder.bind_identifier(
    *,
    source_instance: str,
    identifier: IdentifierDemandDescriptor,
    target_instance: str,
    to: IdentifierSupplyDescriptor,
) -> IdentifierBinding
```

Also add a fluent chain form:

```python
builder.bind_identifier.Consumer.shared.to().Pipeline.Root.Cell.shared
```

This method records a descriptor-level identifier binding:

- source demand: `(source_instance, identifier.ref_path, identifier.name)`
- target supply: `(target_instance, to.ref_path, to.name)`

The fluent form records the same binding shape by collecting the source
instance/path/name and target instance/path/name from attribute access, mirroring
the existing `builder.assign...` chain but using direct binding semantics.

Its semantics are intentionally distinct from `builder.assign(...)`:

- `bind_identifier(...)` resolves the source demand to the same semantic
  identifier binding as the selected supply before hygiene
- if that direct binding is not valid, materialization raises
- it does not fall back to a deterministic assign alias

This keeps output predictable. The same API should not sometimes emit a direct
identifier relationship and sometimes emit an internal alias.

## 3. Why `bind_identifier`

The name should be `bind_identifier`, not plain `bind`.

Astichi already uses `bind` for external compile-time values:

```python
piece.bind(label="ready")
target.add("Step", bind={"label": "ready"})
```

Those surfaces bind `astichi_bind_external(...)` values. Builder identifier
binding is different: it resolves an identifier demand such as
`astichi_import(name)`, `astichi_pass(name)`, or an unresolved
`__astichi_arg__` slot to an identifier supply in the builder graph.

`bind_identifier` also matches the existing composable API:

```python
piece.bind_identifier(shared="shared")
```

The proposed builder method is the descriptor-aware graph-level version of the
same concept.

## 4. Semantics

`builder.bind_identifier(...)` binds a source identifier demand to a
descriptor-selected target identifier supply. Materialization resolves that
binding before final hygiene by making the source identifier nodes participate
in the same semantic scoped binding as the selected supply.

### 4.1 Scope-Aware Direct Binding

The source demand is resolved to the selected supply's identifier binding in the
pre-hygiene AST/shell structure. The implementation should use the same
identifier-demand rewrite path that existing boundary resolution uses, but the
design intent is not "predict the final emitted spelling." The design intent is
"put the identifier nodes in the right semantic scope relationship, then let
hygiene rename normally."

For example, a staged graph may select:

```python
target_instance="Pipeline"
target_ref_path=("Root", "Cell")
outer_name="shared"
```

In the common no-conflict case, final output is naturally direct:

```python
result = []
shared = 10
result.append(shared + 5)
final = tuple(result)
```

This is the primary reason to add `bind_identifier(...)`. It gives the builder a
higher-level binding relation than "publish a qualified assign alias" while
still preserving the normal hygiene pipeline.

### 4.2 Invalid Direct Binding

If the scoped binding cannot be represented validly, materialization raises. It
does not silently fall back to the deterministic assign alias.

Examples of invalid direct binding:

- the selected supply cannot be represented as a name-bearing scoped binding
- the selected supply is not in a scope relationship visible to the source
  contribution
- another visible supply makes the semantic binding ambiguous
- the binding would cross an invalid Python scope boundary
- the selected supply needs expression capture rather than a simple identifier

Use `builder.assign(...)` when the desired behavior is the existing qualified
alias mechanism:

```python
__astichi_assign__inst__Pipeline__ref__Root__ref__Cell__name__shared = shared
result.append(__astichi_assign__inst__Pipeline__ref__Root__ref__Cell__name__shared + 5)
```

That separation keeps the two APIs legible:

- `bind_identifier(...)`: direct descriptor-level identifier binding
- `assign(...)`: explicit graph-qualified wiring, with aliasing where needed

### 4.3 Scoped Binding Conditions

Direct binding is valid only when the materializer can represent the selected
supply and source demand as one scoped identifier relationship before final
hygiene. Initial implementation should require:

- the selected supply is a name-bearing identifier supply
- the selected supply lives in a shell/scope that is visible to the source
  contribution after builder composition
- the demand and supply can be represented before final hygiene without creating
  a graph-qualified alias variable
- no other descriptor-selected supply makes the same source demand ambiguous
- rewriting or annotating the source demand does not cross an invalid Python
  scope boundary
- the supply is not an expression-only capture that needs a temporary alias

Final emitted spelling is explicitly not part of this proof. Hygiene may keep
`shared`, rename another competing scope away, or rename this scope if needed.
The requirement is that all semantically linked uses participate in the same
scope-aware relationship before hygiene runs.

If the scoped relationship cannot be represented, materialization raises and
points the user at `builder.assign(...)` if aliasing is desired.

## 5. Example

Descriptor-driven staged composition currently looks like:

```python
pipeline_desc = pipeline.describe()
consumer_desc = consumer.describe()

consumer_hole = pipeline_desc.single_hole_named("consumers")
shared_demand = next(
    demand
    for demand in consumer_desc.identifier_demands
    if demand.name == "shared"
)
shared_supply = next(
    supply
    for supply in pipeline_desc.identifier_supplies
    if supply.name == "shared" and supply.ref_path == ("Root", "Cell")
)

builder.add("Pipeline", pipeline)
builder.add("Consumer", consumer)
builder.target(consumer_hole.with_root_instance("Pipeline")).add("Consumer")
builder.assign(
    source_instance="Consumer",
    source_ref_path=shared_demand.ref_path,
    inner_name=shared_demand.name,
    target_instance="Pipeline",
    target_ref_path=shared_supply.ref_path,
    outer_name=shared_supply.name,
)
```

With `bind_identifier(...)`:

```python
builder.add("Pipeline", pipeline)
builder.add("Consumer", consumer)
builder.target(consumer_hole.with_root_instance("Pipeline")).add("Consumer")
builder.bind_identifier(
    source_instance="Consumer",
    identifier=shared_demand,
    target_instance="Pipeline",
    to=shared_supply,
)
```

With the fluent chain:

```python
builder.bind_identifier.Consumer.shared.to().Pipeline.Root.Cell.shared
```

Expected materialized source:

```python
result = []
shared = 10
result.append(shared + 5)
final = tuple(result)
```

## 6. Validation

The method should validate:

- `identifier` is an `IdentifierDemandDescriptor`
- `to` is an `IdentifierSupplyDescriptor`
- `source_instance` and `target_instance` are strings
- the referenced source demand exists at
  `(source_instance, identifier.ref_path, identifier.name)`
- the referenced target supply exists at
  `(target_instance, to.ref_path, to.name)`

The final two checks should reuse the existing validation path used by
`builder.assign(...)`.

Different demand and supply names should remain allowed because `assign(...)`
already supports `inner_name != outer_name`.

For direct binding, different names mean the demanded identifier is rewritten
into the supplied identifier's semantic binding. For example:

```python
builder.bind_identifier(
    source_instance="Consumer",
    identifier=local_shared_demand,  # name == "local_shared"
    target_instance="Pipeline",
    to=shared_supply,                # name == "shared"
)
```

resolves uses of `local_shared` in the source demand scope to the selected
`shared` supply's scoped binding.

## 7. Relationship To `assign`

`builder.assign(...)` remains the explicit low-level graph wiring surface.
Existing fluent and named assign calls keep their current behavior.

`builder.bind_identifier(...)` is the descriptor-level surface with direct
binding semantics. Its public contract should not be limited to current assign
alias behavior.

This leaves a clear split:

- keep `assign(...)` as precise low-level wiring
- add `bind_identifier(...)` for descriptor-level binding
- do not make `bind_identifier(...)` silently choose between direct names and
  aliases

## 8. Non-Goals

This proposal does not change external value binding. External bind
descriptors remain satisfied through `.bind(...)` or edge `bind=...`.

This proposal does not remove the deterministic assign alias. The alias remains
part of `builder.assign(...)`.

This proposal does not require descriptor objects or builder binding code to know
final emitted names. Descriptors identify semantic surfaces before
materialization; final spelling is still decided by the existing hygiene pass.

## 9. Public API Impact

Add one public builder proxy:

```python
BuilderHandle.bind_identifier
```

`bind_identifier` should be a property returning a proxy, not a plain method.
The proxy is both callable for data-driven use and an attribute-chain entrypoint
for fluent use, matching the shape of existing builder proxy surfaces.

Both forms should return `IdentifierBinding` directly:

```python
binding = builder.bind_identifier(
    source_instance="Consumer",
    identifier=shared_demand,
    target_instance="Pipeline",
    to=shared_supply,
)

binding = builder.bind_identifier.Consumer.shared.to().Pipeline.Root.Cell.shared
```

Do not add a committed-binding wrapper unless a later implementation need
appears.

No existing API is removed or renamed. Existing fluent assign and named assign
calls continue to work unchanged.

Docs should update:

- `docs/reference/builder-api.md`
- `docs/reference/descriptor-api.md`
- descriptor reference snippets that currently unpack demand/supply descriptors
  manually into `builder.assign(...)`

## 10. Implementation Plan

### 10.1 Add A Binding Record

Add a graph record for descriptor-level identifier bindings.

Recommended shape:

```python
@dataclass(frozen=True)
class IdentifierBinding:
    source_instance: str
    inner_name: str
    target_instance: str
    outer_name: str
    source_ref_path: RefPath = ()
    target_ref_path: RefPath = ()
```

### 10.2 Keep `AssignBinding` Stable

Do not change `AssignBinding` immediately.

Keep `builder.assign(...)` writing `AssignBinding` records and preserve its
existing materialization behavior. This avoids unnecessary churn in existing
goldens and gives the new behavior a clear API boundary.

### 10.3 Add Builder API

Add `bind_identifier(...)` to `BuilderHandle`:

```python
def bind_identifier(
    self,
    *,
    source_instance: str,
    identifier: IdentifierDemandDescriptor,
    target_instance: str,
    to: IdentifierSupplyDescriptor,
) -> IdentifierBinding:
    ...
```

The public property should return a proxy object that supports both:

```python
builder.bind_identifier(
    source_instance="Consumer",
    identifier=shared_demand,
    target_instance="Pipeline",
    to=shared_supply,
)

builder.bind_identifier.Consumer.shared.to().Pipeline.Root.Cell.shared
```

Implementation steps:

1. Validate `identifier` is an `IdentifierDemandDescriptor`.
2. Validate `to` is an `IdentifierSupplyDescriptor`.
3. Normalize `identifier.ref_path` and `to.ref_path`.
4. Reuse the same registered-demand and registered-supplier validation helpers
   used by `builder.assign(...)`.
5. Store an `IdentifierBinding` in `BuilderGraph`.
6. Return the stored binding.

Add `BuilderGraph.add_identifier_binding(...)` with duplicate/conflict behavior
matching `add_assign(...)`: exact duplicates are idempotent, conflicting
bindings for the same `(source_instance, source_ref_path, inner_name)` reject.

The conflict check must also cross-check existing `AssignBinding` records. A
single source demand may not be wired by both `assign(...)` and
`bind_identifier(...)`; otherwise materialization order would silently decide
the result.

The fluent proxy should reuse or closely mirror the existing assign proxy path
machinery:

- source instance selection
- source descendant path selection
- `.to()` transition
- target instance selection
- target descendant path selection
- final supplier-name commit

It should not share commit behavior with assign, because it must write
`IdentifierBinding`, not `AssignBinding`.

The fluent path semantics should match `assign` exactly. A fluent chain such as:

```python
builder.bind_identifier.Pipeline.Root.Inner.local_shared.to().Config.shared
```

records:

```python
IdentifierBinding(
    source_instance="Pipeline",
    source_ref_path=("Root", "Inner"),
    inner_name="local_shared",
    target_instance="Config",
    target_ref_path=(),
    outer_name="shared",
)
```

### 10.4 Materializer Entry Point

Apply identifier bindings before additive edge insertion, in the same phase
where `AssignBinding` records are currently applied. Validate conflicts between
assign and identifier-bind records before applying either kind of wiring.

The current order should become:

```python
_validate_explicit_identifier_wiring_conflicts(...)
_apply_assign_bindings(...)
_apply_identifier_bindings(...)
```

or, if the implementation shares helper code:

```python
_apply_explicit_identifier_wirings(...)
```

The important point is that the source demand is rewritten before the source is
used as an additive contribution. Because conflicts are rejected up front,
`assign` and `bind_identifier` application order should not affect behavior.

### 10.5 Direct Binding Resolution

For each `IdentifierBinding`, materialization should:

1. Resolve the target shell from `(target_instance, target_ref_path)`.
2. Confirm the target shell supplies `outer_name`.
3. Resolve the source shell from `(source_instance, source_ref_path)`.
4. Confirm the source shell demands `inner_name`.
5. Determine whether the target supply and source demand can be represented as
   one scoped identifier relationship before final hygiene.

Initial valid direct case:

- the target supply is a simple identifier supplier collected from the target
  shell body
- the source contribution is inserted into a scope where that target shell's
  identifier binding is visible according to Astichi's shell/scope rules
- no other explicit identifier binding targets the same source demand
- no other descriptor-selected supply makes the same source demand ambiguous
- the source demand can be resolved with the existing
  `_rewrite_identifier_demands_in_body(...)` path or an equivalent
  scope-aware annotation path before final hygiene

If all checks pass:

```python
_rewrite_identifier_demands_in_body(source_body, {inner_name: outer_name})
```

and refresh the source composable/shell index just as assign currently does.
The later hygiene pass remains responsible for any final collision renames.

If any check fails, raise a diagnostic. Do not fall back to assign aliasing from
`bind_identifier(...)`.

### 10.6 Assign Alias Reuse

The existing assign alias helpers should remain owned by `builder.assign(...)`.
`bind_identifier(...)` should not call `_assign_target_alias_name(...)` or
`_publish_assign_target_alias(...)` as fallback behavior.

If a user wants aliasing, the correct API is still:

```python
builder.assign(...)
```

### 10.7 Diagnostics

Add diagnostics for:

- wrong descriptor type for `identifier`
- wrong descriptor type for `to`
- source demand not present at the descriptor path
- target supply not present at the descriptor path
- scoped identifier binding cannot be represented

The invalid-binding diagnostic should include the reason, for example:

- target supply is not visible from the source contribution's scope
- multiple descriptor-selected supplies make the binding ambiguous
- selected supply requires expression capture
- binding would cross an invalid Python scope boundary

### 10.8 Tests

Add focused tests for:

- `bind_identifier(...)` records descriptor demand/supply paths correctly
- fluent `builder.bind_identifier.Consumer.shared.to().Pipeline.Root.Cell.shared`
  records the same binding as the data-driven form
- exact duplicate binding is idempotent
- conflicting binding rejects
- wrong descriptor type rejects
- unknown source demand path rejects
- unknown target supply path rejects
- simple staged descriptor binding materializes directly:

  ```python
  result = []
  shared = 10
  result.append(shared + 5)
  final = tuple(result)
  ```

- invalid direct binding raises with a useful diagnostic
- existing `builder.assign(...)` tests and goldens remain unchanged

Prefer canonical reference snippets/goldens for successful end-to-end behavior,
especially multi-build-stage behavior. Bespoke unit tests should focus on graph
recording, conflict detection, descriptor type validation, and diagnostics that
the golden/reference harness cannot express cleanly.

Success-oriented golden/reference coverage should include:

- single-stage direct identifier binding
- two-stage descriptor binding where a stage-2 source binds to a stage-1
  descendant supply
- three-stage or nested staged binding where descriptor `ref_path` values are
  non-empty on both the demand or supply side where applicable
- a staged case with a same-name local collision that demonstrates normal
  hygiene still renames scopes coherently after `bind_identifier(...)`
- the existing assign-alias staged case, kept separate, to show
  `builder.assign(...)` remains the alias-producing surface

### 10.9 Reference Snippets

Update the staged descriptor reference snippet to use:

```python
builder.bind_identifier(
    source_instance="Consumer",
    identifier=shared_demand,
    target_instance="Pipeline",
    to=shared_supply,
)
```

Its materialized golden should prefer:

```python
result = []
shared = 10
result.append(shared + 5)
final = tuple(result)
```

Keep a separate assign-focused snippet or test if the explicit assign alias
behavior still needs public illustration.

### 10.10 Documentation

Update:

- `docs/reference/builder-api.md`: add `bind_identifier(...)` signature and
  fluent form, and contrast direct binding with `assign(...)`
- `docs/reference/descriptor-api.md`: show descriptor demand/supply binding with
  `bind_identifier(...)`
- `docs/guide/using-the-api.md`: use `bind_identifier(...)` in the staged
  descriptor example
- `docs/reference/snippets/descriptor_api/`: regenerate goldens

### 10.11 Rollout Order

Recommended order:

1. Add `IdentifierBinding` and graph storage.
2. Add callable `BuilderHandle.bind_identifier(...)` with validation and
   storage.
3. Add fluent `builder.bind_identifier...` proxy chain that records the same
   binding shape.
4. Implement scope-aware materializer support for the initial valid staged
   binding cases.
5. Add diagnostics for invalid scoped identifier binding.
6. Add tests for data-driven API, fluent API, validation, diagnostics, and
   direct materialization, with successful multi-stage behavior covered through
   golden/reference tests.
7. Update snippets and docs.
8. Regenerate materialized reference outputs.
