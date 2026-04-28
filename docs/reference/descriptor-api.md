# Descriptor API

`Composable.describe()` returns immutable metadata for data-driven composition.
It exposes the attachment surfaces Astichi can already validate: additive
holes, ports, external binds, identifier wiring surfaces, and conservative
port-backed productions.

```python
description = composable.describe()

for hole in description.holes:
    print(hole.name, hole.address.ref_path, hole.add_policy.is_multi_addable())
```

## Holes

`ComposableHole` describes a builder-additive target.

```python
hole = root.describe().single_hole_named("body")

builder = astichi.build()
builder.add("Root", root)
builder.add("Step", step)
builder.target(hole.with_root_instance("Root")).add("Step", order=0)
```

Each hole has:

- `name`: authored target name
- `descriptor`: shape/placement compatibility surface
- `address`: `TargetAddress(root_instance, ref_path, target_name, leaf_path)`
- `port`: structural demand port descriptor
- `add_policy`: behavior-bearing cardinality policy

`root_instance` is `None` until the composable is registered in a builder.
Pass `hole.with_root_instance("Name")` or
`hole.address.with_root_instance("Name")` before using it with
`builder.target(...)`.

## Add Policy

`SINGLE_ADD` and `MULTI_ADD` are behavior-bearing singleton policies, not enum
values. Ask the object:

```python
hole.add_policy.accepts_next_addition(current_count)
hole.add_policy.is_multi_addable()
```

Current mapping:

- block holes: multi-add
- `*astichi_hole(...)` and `**astichi_hole(...)`: multi-add
- function parameter holes: multi-add
- scalar expression holes: single-add

Build and materialize remain authoritative; descriptors are planning metadata.

## Ports And Binds

`PortDescriptor` exposes `name`, `shape`, `placement`, `mutability`, and
`origins` using the same behavior-bearing semantic objects as the internal
model.

`description.external_binds` lists `astichi_bind_external(...)` demands.
`description.identifier_demands` and `description.identifier_supplies` list
explicit identifier wiring surfaces with shell `ref_path` metadata.

## Descendant Paths

For built composables, descriptor addresses use the same shell-ref paths as the
builder fluent API:

```python
hole.address.ref_path == ("Root", "Inner")
builder.target(hole.with_root_instance("Pipeline")).add("Step")
```

is equivalent to:

```python
builder.Pipeline.Root.Inner.<hole_name>.add.Step()
```

## Productions

`description.productions` is conservative and mirrors existing materialize
paths:

- ordinary non-payload snippets expose a block production
- snippets that are accepted as implicit expression sources expose an
  expression production
- `astichi_funcargs(...)` payload snippets expose an expression-family
  production for compatible `*` / `**` call-argument holes
- `astichi_params(...)` payload snippets expose their parameter production
- identifier exports are identifier supplies, not additive productions

Use `description.productions_compatible_with(hole)` to filter a composable's
productions against a hole. Use materialize/build validation as the final
compatibility check.

## Known Ambiguity

Unrolled holes currently describe their source-visible target name. For
example, an unfilled unrolled hole named `slot__iter_0` is exposed as
`TargetAddress(target_name="slot__iter_0", leaf_path=())`.

The alternative `TargetAddress(target_name="slot", leaf_path=(0,))` is
ambiguous without retained unroll provenance or a rule reserving
`__iter_<n>` suffixes for generated holes, because a user can author a hole
with that literal name.
