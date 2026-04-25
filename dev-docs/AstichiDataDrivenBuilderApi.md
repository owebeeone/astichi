# Astichi Data-Driven Builder API

Status: implemented.

## 1. Problem

The current builder API is optimized for handwritten composition examples:

```python
builder.add.Step[2](piece)
builder.Root.body.add.Step[2](order=2)
builder.Pipeline.Root.Loop.slot[0].add.Step0(order=0)
builder.assign.Step1.total.to().Root.total
```

That fluent surface is useful for tests, docs, and quick experiments, but it
creates identifiers dynamically through Python attribute access. That is a poor
fit for data-driven generation systems such as YIDL, where instance names,
target names, ref-path segments, indexes, and binding data come from resolved
spec records.

YIDL should not synthesize Python attribute chains to call Astichi. The builder
needs a first-class named API that follows the same path semantics as the
fluent API while accepting ordinary data values.

## 2. Goal

Add a public data-driven builder surface where every fluent operation has a raw
named equivalent.

The guiding rule:

> The fluent builder is a DSL over a plain named API.

The named API must:

1. Preserve current fluent builder semantics.
2. Accept names, path segments, indexes, binds, identifier binds, and keep names
   as ordinary data.
3. Reuse the same internal graph records: `InstanceRecord`, `TargetRef`,
   `AdditiveEdge`, `EdgeSourceOverlay`, and `AssignBinding`.
4. Keep all existing validation and diagnostics at the same layer.
5. Be suitable for mapper/rule engines, not only unit tests.

## 3. Non-Goals

1. Do not remove or deprecate the fluent API.
2. Do not add replacement semantics.
3. Do not change additive ordering.
4. Do not change hygiene, marker lowering, or materialization semantics.
5. Do not expose `BuilderGraph` mutation as the normal public API.

## 4. Proposed Surface

### 4.1 Register Instances

Current fluent:

```python
builder.add.Root(root)
builder.add.Step[2](piece)
```

Named equivalent:

```python
builder.add("Root", root)
builder.add("Step", piece, indexes=(2,))
```

Signature:

```python
builder.add(
    name: str,
    composable: Composable,
    *,
    indexes: int | tuple[int, ...] | None = None,
    arg_names: Mapping[str, str] | None = None,
    keep_names: Iterable[str] | None = None,
) -> InstanceHandle
```

This is the public call shape, not a replacement for the existing
`BuilderHandle.add` property. `builder.add` still returns an `AddProxy`; the
proxy becomes callable, so `builder.add("Root", root)` and
`builder.add.Root(root)` are two surfaces over the same operation.

`indexes=None` registers a base instance. `indexes=(2,)` registers the same
family member that fluent `builder.add.Step[2](...)` registers.

### 4.2 Select Instances

Current fluent:

```python
builder.Root
builder.Step[2]
```

Named equivalent:

```python
builder.instance("Root")
builder.instance("Step", indexes=(2,))
```

Signature:

```python
builder.instance(
    name: str,
    *,
    indexes: int | tuple[int, ...] | None = None,
) -> InstanceHandle
```

The selected handle is the same kind of `InstanceHandle` returned by fluent
attribute access.

### 4.3 Walk Target Paths

Current fluent:

```python
builder.Root.body
builder.Pipeline.Root.Loop.slot[0]
```

Named equivalent:

```python
builder.instance("Root").target("body")
builder.instance("Pipeline").target("Root").target("Loop").target("slot").index(0)
```

Signatures:

```python
InstanceHandle.target(name: str) -> TargetHandle
TargetHandle.target(name: str) -> TargetHandle
TargetHandle.index(*indexes: int) -> TargetHandle
```

`target(name)` performs the same hop as one fluent `.<name>` segment:

- on an `InstanceHandle`, it names the first target leaf under the root
  instance
- on a `TargetHandle`, it first resolves the previous leaf as a descendant
  insert shell, then makes `name` the new target leaf

`index(...)` performs the same leaf-path operation as fluent `[i]` on a
`TargetHandle`. `.index(0, 1)` is equivalent to fluent `[0, 1]`, and chained
`.index(0).index(1)` accumulates the same leaf path.

### 4.4 Add To Targets

Current fluent:

```python
builder.Root.body.add.Step(order=0)
builder.Root.body.add.Step[2](order=2, arg_names={"field": "count"})
```

Named equivalent:

```python
builder.instance("Root").target("body").add("Step", order=0)
builder.instance("Root").target("body").add(
    "Step",
    indexes=(2,),
    order=2,
    arg_names={"field": "count"},
)
```

Signature:

```python
TargetHandle.add(
    source: str,
    *,
    indexes: int | tuple[int, ...] | None = None,
    order: int = 0,
    arg_names: Mapping[str, str] | None = None,
    keep_names: Iterable[str] | None = None,
    bind: Mapping[str, object] | None = None,
) -> AdditiveEdge
```

This is the public call shape after `TargetHandle.add` returns its existing
`AddToTargetProxy`. The proxy becomes callable, so `target.add("Source", ...)`
and `target.add.Source(...)` are the same operation.

### 4.5 Assign Boundary Bindings

Current fluent:

```python
builder.assign.Step1.total.to().Root.total
builder.assign.Pipeline.Root.events.to().Root.out
```

Named equivalent:

```python
builder.assign(
    source_instance="Step1",
    inner_name="total",
    target_instance="Root",
    outer_name="total",
)

builder.assign(
    source_instance="Pipeline",
    source_ref_path=("Root",),
    inner_name="events",
    target_instance="Root",
    outer_name="out",
)
```

Signature:

```python
builder.assign(
    *,
    source_instance: str,
    inner_name: str,
    target_instance: str,
    outer_name: str,
    source_ref_path: tuple[str | int, ...] = (),
    target_ref_path: tuple[str | int, ...] = (),
) -> AssignBinding
```

This is the public call shape, not a replacement for the existing
`BuilderHandle.assign` property. `builder.assign` still returns an
`AssignProxy`; the proxy becomes callable for named data-driven use.

The named assign path must produce the same `AssignBinding` as the fluent
chain, with the same path normalization and demand/supplier validation
semantics. Any shared validation should be factored out before the helper calls
into `BuilderGraph.add_assign(...)`. The fluent assign chain remains as the
human-facing DSL.

## 5. Naming And Validation

The named API should validate through the same raw graph helpers as the fluent
API. It should not duplicate builder rules.

Important details:

1. Instance names use the same base/family rule as fluent instance names.
2. `indexes` normalize through the same indexed-family helper as fluent
   `[i]`.
3. Target path segments normalize through `normalize_ref_path(...)`.
4. Edge overlays use the same edge-local `EdgeSourceOverlay` behavior.
5. A named API call must produce the same graph record as the equivalent
   fluent API call.

Leading-underscore names are a special case. Fluent `__getattr__` rejects them
because Python reserves those names for object protocol behavior. The named API
may accept any valid identifier that the raw graph accepts, including leading
underscores, because the name is now explicit data rather than an attribute
lookup. Leading-underscore names are only available through explicit named API
calls; fluent attribute access continues to reject them.

## 6. Direct TargetRef Helper

The path-following API should be the normal data-driven surface because it
matches fluent builder behavior. A small direct helper is still useful for
systems that already hold a normalized target reference.

Proposed helper:

```python
builder.target(
    *,
    root_instance: str,
    target_name: str,
    ref_path: tuple[str | int, ...] = (),
    leaf_path: int | tuple[int, ...] | None = None,
) -> TargetHandle
```

This should construct the same `TargetHandle` that the path-following API
would have produced. `leaf_path` names the indexed path on the target leaf and
normalizes like `TargetHandle.index(...)`.

## 7. Equivalence Table

| Fluent | Named |
| --- | --- |
| `builder.add.Root(root)` | `builder.add("Root", root)` |
| `builder.add.Step[2](piece)` | `builder.add("Step", piece, indexes=(2,))` |
| `builder.Root` | `builder.instance("Root")` |
| `builder.Step[2]` | `builder.instance("Step", indexes=(2,))` |
| `builder.Root.body` | `builder.instance("Root").target("body")` |
| `builder.Pipeline.Root.Loop.slot[0]` | `builder.instance("Pipeline").target("Root").target("Loop").target("slot").index(0)` |
| `builder.Root.body.add.Step(order=0)` | `builder.instance("Root").target("body").add("Step", order=0)` |
| `builder.Root.body.add.Step[2](order=2)` | `builder.instance("Root").target("body").add("Step", indexes=(2,), order=2)` |
| `builder.assign.Step1.total.to().Root.total` | `builder.assign(source_instance="Step1", inner_name="total", target_instance="Root", outer_name="total")` |

## 8. YIDL Mapper Shape

With this API, a YIDL generation rule can carry plain data:

```python
Contribution(
    source="SlotItem",
    target_root="Main",
    target_ref_path=("__slots__",),
    target_name="items",
    order=field.order,
    bind={"slot_name": field.name},
)
```

and lower it without dynamic attribute construction:

```python
builder.target(
    root_instance=contribution.target_root,
    ref_path=contribution.target_ref_path,
    target_name=contribution.target_name,
).add(
    contribution.source,
    order=contribution.order,
    bind=contribution.bind,
    arg_names=contribution.arg_names,
    keep_names=contribution.keep_names,
)
```

The mapper remains data in, graph operations out.

## 9. Implementation Notes

The implementation should be small because most behavior already exists behind
the fluent API.

Expected changes:

1. Make `AddProxy` callable and delegate to `_NamedAdder`.
2. Add `BuilderHandle.instance(...)`.
3. Add `BuilderHandle.target(...)`.
4. Add `InstanceHandle.target(...)`.
5. Add `TargetHandle.target(...)`.
6. Add `TargetHandle.index(...)`.
7. Make `AddToTargetProxy` callable and delegate to `_NamedTargetAdder`.
8. Make `AssignProxy` callable; normalize paths and share fluent assign
   validation before constructing `AssignBinding` through
   `BuilderGraph.add_assign(...)`.
9. Factor any duplicated name/index normalization into small helpers.

Fluent methods should become wrappers over the named methods where doing so
keeps the code clearer.

## 10. Test Plan

Use success-path goldens for the main behavior.

Gold source cases:

1. Basic named API registration and target wiring.
2. Indexed instance family registration and indexed source wiring.
3. Nested target path with indexed target leaf.
4. Edge-local `arg_names`, `keep_names`, and `bind`.
5. Named assign binding with root and nested ref paths.

Bespoke tests should stay narrow:

1. Named API and fluent API produce equivalent `BuilderGraph` records for a
   small graph.
2. Invalid names and invalid indexes produce useful diagnostics.
3. Leading-underscore explicit names are accepted or rejected according to the
   final normalization rule.

## 11. Documentation Plan

After implementation:

1. Update `docs/reference/builder-api.md`.
2. Add one concise reference snippet showing the named API beside fluent API.
3. Update `AstichiSingleSourceSummary.md` so the builder section states that
   fluent calls are sugar over the named API.
4. Keep existing fluent examples; do not churn them unless the named API is
   more appropriate for the lesson.
