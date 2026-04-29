# Descriptor API

`Composable.describe()` returns immutable metadata for planning data-driven
composition. The descriptor API does not materialize code by itself; it exposes
the same attachment, binding, and compatibility surfaces that the builder and
materializer already validate.

Use descriptors when a tool needs to inspect a composable before deciding how to
wire it:

```python
description = composable.describe()

for hole in description.holes:
    print(hole.name, hole.address.ref_path, hole.add_policy.is_multi_addable())
```

The root package exports `ComposableDescription`, `ComposableHole`, and
`TargetAddress`. The richer descriptor value objects and semantic singletons
are exported from `astichi.model`.

## Composition Workflow

A typical descriptor-driven composition pipeline is:

1. Compile or build composables.
2. Call `.describe()` on candidate roots and payloads.
3. Select a `ComposableHole`.
4. Filter candidate payloads with `.productions_compatible_with(hole)`.
5. Register the pieces with the builder.
6. Add a root instance to the hole address with `.with_root_instance(...)`.
7. Pass the resolved descriptor address to `builder.target(...)`.

```python
root = astichi.compile(
    """
def run(params__astichi_param_hole__):
    return fn(*astichi_hole(args))
"""
)
params = astichi.compile(
    """
def astichi_params(value):
    pass
"""
)
args = astichi.compile("astichi_funcargs(value)\n")

root_desc = root.describe()
params_hole = root_desc.single_hole_named("params")
args_hole = root_desc.single_hole_named("args")

if not params.describe().productions_compatible_with(params_hole):
    raise ValueError("params cannot satisfy params hole")
if not args.describe().productions_compatible_with(args_hole):
    raise ValueError("args cannot satisfy args hole")

builder = astichi.build()
builder.add("Root", root)
builder.add("Params", params)
builder.add("Args", args)
builder.target(params_hole.with_root_instance("Root")).add("Params")
builder.target(args_hole.with_root_instance("Root")).add("Args")
result = builder.build()
```

Build and materialize remain authoritative. Descriptor compatibility is intended
for planning, filtering, and diagnostics before the final builder validation
runs.

## `ComposableDescription`

`ComposableDescription` is the top-level return value from
`Composable.describe()`.

Fields:

| Field | Meaning |
| --- | --- |
| `holes` | Additive target surfaces addressable with `builder.target(...).add(...)`. |
| `demand_ports` | Raw demand-side port descriptors. |
| `supply_ports` | Raw supply-side port descriptors. |
| `external_binds` | `astichi_bind_external(...)` values that can be supplied with `.bind(...)` or edge `bind=...`. |
| `identifier_demands` | Identifier imports/pass/arg demands addressable with builder `assign(...)` or edge `arg_names=...`. |
| `identifier_supplies` | Identifier exports/readable names addressable as assign targets. |
| `productions` | Surfaces this composable can contribute to compatible holes. |

Helpers:

```python
description.holes_named("body")          # tuple[ComposableHole, ...]
description.single_hole_named("body")    # exactly one or ValueError
description.productions_compatible_with(hole)
```

`productions_compatible_with(hole)` returns the subset of
`description.productions` whose `ProductionDescriptor.satisfies(...)` result is
accepted for `hole.descriptor`.

## `ComposableHole`

`ComposableHole` describes one builder-additive target.

Fields:

| Field | Meaning |
| --- | --- |
| `name` | Authored target name, such as `body`, `args`, or `params`. |
| `descriptor` | A `HoleDescriptor` containing structural compatibility data. |
| `address` | A `TargetAddress` usable with `builder.target(...)` after root resolution. |
| `port` | The demand-side `PortDescriptor` for the hole. |
| `add_policy` | `SINGLE_ADD` or `MULTI_ADD`, exposed as behavior-bearing singleton objects. |

Helpers:

```python
resolved = hole.with_root_instance("Root")
hole.is_multi_addable()
```

`with_root_instance(...)` returns a new `ComposableHole` with the same
descriptor data and a resolved address. It does not mutate the original
description.

## `TargetAddress`

`TargetAddress` is the generic address for a builder target hole.

Constructor fields:

```python
TargetAddress(
    target_name: str,
    root_instance: str | None = None,
    ref_path: tuple[str | int, ...] = (),
    leaf_path: tuple[int, ...] = (),
)
```

Prefer keyword construction for clarity:

```python
TargetAddress(
    root_instance="Pipeline",
    ref_path=("Root", "Loop"),
    target_name="slot",
    leaf_path=(0,),
)
```

Field meanings:

| Field | Meaning |
| --- | --- |
| `root_instance` | Builder instance name that owns the root composable. Descriptor output uses `None` until a builder instance is known. |
| `ref_path` | Descendant shell path inside a staged/built composable. |
| `target_name` | Leaf hole name. |
| `leaf_path` | Loop/index path on the leaf target. |

`TargetAddress.with_root_instance("Name")` returns a new address with the root
instance filled in.

## Addressing Builder Targets

`builder.target(...)` accepts either a resolved `TargetAddress`, a resolved
`ComposableHole`, or explicit keyword address fields:

```python
builder.target(hole.with_root_instance("Pipeline")).add("Step")

builder.target(
    root_instance="Pipeline",
    ref_path=("Root", "Inner"),
    target_name="slot",
).add("Step")
```

Passing an unresolved descriptor address raises because the builder cannot know
which registered instance owns the target:

```python
hole = root.describe().single_hole_named("body")
builder.target(hole)  # ValueError: root_instance is unresolved
```

If a descriptor address is supplied with keyword overrides, each override must
match the descriptor value. Conflicting `root_instance`, `target_name`,
`ref_path`, or `leaf_path` values raise.

## Descendant Paths

For built composables, descriptor addresses use the same shell-ref paths as the
builder fluent API:

```python
stage1 = astichi.build()
stage1.add("Root", astichi.compile("astichi_hole(body)\n"))
stage1.add("Inner", astichi.compile("astichi_hole(slot)\n"))
stage1.instance("Root").target("body").add("Inner")
built = stage1.build()

hole = built.describe().single_hole_named("slot")
assert hole.address.ref_path == ("Root", "Inner")

stage2 = astichi.build()
stage2.add("Pipeline", built)
stage2.add("Step", astichi.compile("value = 1\n"))
stage2.target(hole.with_root_instance("Pipeline")).add("Step")
```

The last line is equivalent to the fluent chain:

```python
stage2.Pipeline.Root.Inner.slot.add.Step()
```

Multi-level fluent paths such as `builder.Root.Previous.foo.add.Step(...)`
therefore map directly to descriptor target data:

```python
builder.target(
    root_instance="Root",
    ref_path=("Previous",),
    target_name="foo",
).add("Step")
```

## Add Policy

`SINGLE_ADD` and `MULTI_ADD` are public behavior-bearing singleton policies.
They are not enum values and callers should ask the object for behavior:

```python
hole.add_policy.accepts_next_addition(current_count)
hole.add_policy.is_multi_addable()
```

Current mapping:

| Hole surface | Policy |
| --- | --- |
| Block hole, `astichi_hole(body)` as a statement | `MULTI_ADD` |
| Positional variadic call-argument hole, `*astichi_hole(args)` | `MULTI_ADD` |
| Named variadic call-argument hole, `**astichi_hole(kwargs)` | `MULTI_ADD` |
| Function parameter hole, `name__astichi_param_hole__` | `MULTI_ADD` |
| Scalar expression hole, `value = astichi_hole(expr)` | `SINGLE_ADD` |

`accepts_next_addition(current_count)` raises for negative counts. For
`SINGLE_ADD`, only count `0` is accepted. For `MULTI_ADD`, every non-negative
count is accepted.

## Ports

`PortDescriptor` is the immutable public view of a demand or supply port.

Fields:

| Field | Meaning |
| --- | --- |
| `name` | Port name. |
| `shape` | Marker shape object, such as block, scalar expression, variadic argument, parameter, or identifier. |
| `placement` | Behavior-bearing placement object. Definition parameters and call arguments are different placements. |
| `mutability` | Behavior-bearing mutability object. |
| `origins` | `PortOrigins` object describing why the port exists. |

Helpers:

```python
port.is_external_bind_demand()
port.is_identifier_demand()
port.is_identifier_supply()
demand_port.accepts_supply(supply_port)
```

`accepts_supply(...)` returns a compatibility object. Use
`.is_accepted()` on that result instead of comparing semantic tags manually.

## Holes And Productions

`HoleDescriptor` is the compatibility surface for a hole.

Fields and helpers:

```python
hole_descriptor.port
hole_descriptor.shape
hole_descriptor.placement
hole_descriptor.accepts(production)
```

`ProductionDescriptor` is a surface that a composable can contribute to a
compatible additive hole.

Fields and helpers:

```python
production.name
production.port
production.payload       # astichi_funcargs payload metadata, or None
production.expression    # concrete expression AST for expression checks, or None
production.satisfies(hole_descriptor)
production.is_identifier_supply()
```

`description.productions` is conservative and mirrors existing materialize
paths:

| Source composable form | Production behavior |
| --- | --- |
| Ordinary non-payload snippet | Block production. |
| Snippet accepted as an implicit expression source | Expression production, and also block production where valid. |
| `astichi_funcargs(...)` payload snippet | Expression-family production checked against compatible `*` / `**` call-argument holes. |
| `astichi_params(...)` payload snippet | Parameter production. |
| Identifier export | Identifier supply descriptor, not an additive production. |

Use `production.satisfies(hole.descriptor).is_accepted()` for one production, or
`description.productions_compatible_with(hole)` to filter all productions from a
candidate composable.

## Function Argument Productions

`astichi_funcargs(...)` production descriptors are region-aware:

```python
root = astichi.compile(
    "result = fn(*astichi_hole(args), **astichi_hole(kwargs))\n"
)
args = root.describe().single_hole_named("args")
kwargs = root.describe().single_hole_named("kwargs")

positional = astichi.compile("astichi_funcargs(first)\n").describe()
keyword = astichi.compile("astichi_funcargs(named=value)\n").describe()
mixed = astichi.compile("astichi_funcargs(first, named=value)\n").describe()

assert positional.productions_compatible_with(args)
assert not positional.productions_compatible_with(kwargs)
assert keyword.productions_compatible_with(kwargs)
assert not keyword.productions_compatible_with(args)
assert not mixed.productions_compatible_with(args)
assert not mixed.productions_compatible_with(kwargs)
```

Named variadic expression holes require dict-display expression inserts:

```python
entries = astichi.compile(
    "result = {**astichi_hole(entries)}\n"
).describe().single_hole_named("entries")

assert astichi.compile("{key: value}\n").describe().productions_compatible_with(entries)
assert not astichi.compile("value\n").describe().productions_compatible_with(entries)
```

## External Binds

`ExternalBindDescriptor` describes one `astichi_bind_external(...)` demand.

Fields:

| Field | Meaning |
| --- | --- |
| `name` | External value name. |
| `port` | Demand-side `PortDescriptor`. |
| `already_bound` | Whether the composable being described has already supplied this bind. |

Use descriptors to discover required bind values, then bind directly on the
composable or as an edge overlay:

```python
piece = astichi.compile(
    """
config = astichi_bind_external(config)
print(config)
"""
)

bind_names = [item.name for item in piece.describe().external_binds]
bound = piece.bind({name: values[name] for name in bind_names})

builder.add("Step", piece)
builder.instance("Root").target("body").add(
    "Step",
    bind={name: values[name] for name in bind_names},
)
```

## Identifier Wiring

`IdentifierDemandDescriptor` describes an identifier demand such as
`astichi_import(name)`, `astichi_pass(name)`, or an unresolved
`__astichi_arg__` slot.

Fields:

| Field | Meaning |
| --- | --- |
| `name` | Inner demanded identifier name. |
| `port` | Demand-side `PortDescriptor`. |
| `ref_path` | Descendant shell path where the demand lives. |

`IdentifierSupplyDescriptor` describes an identifier supply such as
`astichi_export(name)` or another readable supplier.

Fields:

| Field | Meaning |
| --- | --- |
| `name` | Supplied identifier name. |
| `port` | Supply-side `PortDescriptor`. |
| `ref_path` | Descendant shell path where the supply lives. |

The descriptor paths map directly to `builder.bind_identifier(...)`:

```python
source_desc = source_piece.describe()
target_desc = target_piece.describe()
demand = source_desc.identifier_demands[0]
supply = target_desc.identifier_supplies[0]

builder.bind_identifier(
    source_instance="Step",
    identifier=demand,
    target_instance="Pipeline",
    to=supply,
)
```

`bind_identifier(...)` is scope-aware and direct: it resolves the source demand
to the selected supply before final hygiene. Use `builder.assign(...)` instead
when you want graph-qualified alias wiring.

For simple edge-local identifier resolution, use `arg_names=...` on
`target.add(...)`:

```python
builder.instance("Root").target("body").add(
    "Step",
    arg_names={"total": "total"},
)
```

Use `bind_identifier(...)` when the demand and supply descriptors should
participate in the same scoped identifier binding. Use `assign(...)` for the
lower-level graph-qualified alias surface. Use edge `arg_names=...` when the
identifier should be resolved as part of one additive edge.

## Public Exports

Common imports:

```python
from astichi import ComposableDescription, ComposableHole, TargetAddress
from astichi.model import (
    AddPolicy,
    ExternalBindDescriptor,
    HoleDescriptor,
    IdentifierDemandDescriptor,
    IdentifierSupplyDescriptor,
    MULTI_ADD,
    PortDescriptor,
    ProductionDescriptor,
    SINGLE_ADD,
)
```

The root package intentionally exports only the descriptor types most directly
needed by data-driven builders. Advanced inspection code should import the full
descriptor set from `astichi.model`.

## Reference Snippets

Runnable descriptor examples live under
[`snippets/descriptor_api/`](snippets/descriptor_api/):

- [`external_bind_single/`](snippets/descriptor_api/external_bind_single/) uses
  `description.external_binds` to bind a single composable before materializing.
- [`staged_descriptor_targets/`](snippets/descriptor_api/staged_descriptor_targets/)
  uses descriptor hole addresses with `builder.target(...)` and descriptor
  identifier paths with `builder.bind_identifier(...)`.
- [`unrolled_indexed_descriptor_targets/`](snippets/descriptor_api/unrolled_indexed_descriptor_targets/)
  resolves a descriptor target once, then uses `target[i]` and indexed source
  instances for loop-expanded holes.

## Known Ambiguity

Unrolled holes currently describe their source-visible target name. For
example, an unfilled unrolled hole named `slot__iter_0` is exposed as:

```python
TargetAddress(target_name="slot__iter_0", leaf_path=())
```

The alternative:

```python
TargetAddress(target_name="slot", leaf_path=(0,))
```

is ambiguous without retained unroll provenance or a rule reserving
`__iter_<n>` suffixes for generated holes, because a user can author a hole with
that literal name.
