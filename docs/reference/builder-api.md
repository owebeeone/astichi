# Builder API

## Entry

```python
from astichi import build

builder = build()
```

**`build()`** returns a **mutable builder** graph. The builder holds **named
instances** of `Composable`, **ties** (edges from supply to demand ports), and
**ordering** metadata for variadic insertion sites.

## Fluent API

The current handle API is fluent at the **operation** level, but not as one
long expression across repeated `.add.<Name>(...)` calls. A working pattern is:

```python
builder = build()
builder.add.A(loop_example)
builder.add.B(print_example)
builder.A.init.add.B(order=10)
builder.A.first[0].add.B(order=10)
builder.A.third.add.B(order=10)

result = builder.build()
```

Indexed instance families are also supported:

```python
builder = build()
builder.add.Step[0](step0)
builder.add.Step[1](step1)
builder.add.Helper(helper)

builder.Root.body.add.Step[0](order=0)
builder.Root.body.add.Step[1](order=1)
builder.Step[1].extra.add.Helper(order=0)
```

Descendant addressing uses the same fluent path shape:

```python
builder.Pipeline.Root.Parse.body.add.Step(order=0)
builder.Pipeline.Root.Parse.rows[1, 2].Normalize.body.add.Step(order=10)
builder.assign.Step.total.to().Pipeline.Root.Right.total
```

On the target-adder surface, specialization is **edge-local**:

- `builder.Target.hole.add.Source(arg_names=..., keep_names=...)` affects only
  that additive edge
- `builder.Target.hole.add.Source(bind={...})` applies `astichi_bind_external`
  values only for that edge
- the registered `Source` instance is not mutated by those edge-local overlays
- `builder.add.Source[i](piece)` registers a distinct indexed family member,
  and `builder.Target.hole.add.Source[i](...)` selects that member as the
  source instance for one edge

Indexed family rule:

- a stem is either a base instance (`Step`) or an indexed family
  (`Step[i]`), never both
- if a family exists and no base instance of the same stem exists,
  `builder.Step[i]` selects that family member for later wiring
- after selection, `builder.Step[i]` behaves like an ordinary instance handle,
  so descendant addressing continues as usual

Named descendant hops come from shells preserved across earlier `build()`
stages. A stage-built composable exposes its preserved build root name as the
first descendant segment; index segments attach to the immediately preceding
descendant/leaf.

For registered instances, the fluent surface validates descendant refs eagerly:

- unknown descendant hops reject
- deep target/source leaves inside a resolved descendant shell reject when the
  named hole or identifier slot does not exist
- reused built composables with duplicate full descendant refs reject at
  `builder.add.<Name>(...)`

## Handle-oriented API (equivalent semantics)

The same graph can be built with **stable handle objects** instead of a single
chain:

```python
b = build()
b.add.A(loop_example)
b.add.B(print_example)

a = b.A
a.init.add.B(order=10)
a.first[0].add.B(order=10)
a.third.add.B(order=10)

result = b.build()
```

Fluent and handle styles **must** behave identically (**[§8](../../dev-docs/historical/AstichiApiDesignV1.md)**).

## Data-driven named API

The fluent builder is a DSL over a named API. Use the named API when builder
instance names, target paths, indexed family members, edge overlays, or assign
bindings come from resolved data records instead of handwritten Python
attribute chains.

```python
b = build()
b.add("Root", root_piece)
b.add("Step", step_piece, indexes=(2,))

b.instance("Root").target("body").add(
    "Step",
    indexes=(2,),
    order=10,
    bind={"seed": 1},
)

b.assign(
    source_instance="Step",
    inner_name="total",
    target_instance="Root",
    outer_name="total",
)
```

`builder.add`, `target.add`, and `builder.assign` remain proxy properties for
the fluent API; the proxies are also callable for named/data-driven use. Named
calls reuse the same graph records and validation paths as fluent calls.

Reference signatures:

```python
builder.add(
    name,
    composable,
    *,
    indexes=None,
    arg_names=None,
    keep_names=None,
)

builder.instance(name, *, indexes=None)
builder.instance("Root").target("body")
builder.instance("Root").target("body").index(0)

target.add(
    source,
    *,
    indexes=None,
    order=0,
    arg_names=None,
    keep_names=None,
    bind=None,
)

builder.target(
    address=None,
    *,
    root_instance=None,
    ref_path=None,
    target_name=None,
    leaf_path=None,
)

builder.assign(
    *,
    source_instance,
    inner_name,
    target_instance,
    outer_name,
    source_ref_path=(),
    target_ref_path=(),
)

builder.bind_identifier(
    *,
    source_instance,
    identifier,
    target_instance,
    to,
)
```

`arg_names`, `keep_names`, and `bind` are overlays for the registered source
piece on that specific edge. They use the same semantics as
`BasicComposable.bind(...)`, identifier binding, and keep-name preservation, but
the overlay is scoped to the edge rather than changing the registered
composable.

Leading-underscore names are only available through explicit named calls:

```python
b.add("_Root", root_piece)
b.add("_Step", step_piece)
b.instance("_Root").target("_slot").add("_Step")
```

Fluent attribute access still rejects leading-underscore names because those
names collide with Python object protocol behavior.

### Fluent vs data-driven equivalence

| Fluent | Data-driven named API |
| --- | --- |
| `builder.add.Root(root)` | `builder.add("Root", root)` |
| `builder.add.Step[2](piece)` | `builder.add("Step", piece, indexes=(2,))` |
| `builder.Root` | `builder.instance("Root")` |
| `builder.Step[2]` | `builder.instance("Step", indexes=(2,))` |
| `builder.Root.body` | `builder.instance("Root").target("body")` |
| `builder.Pipeline.Root.Loop.slot[0]` | `builder.instance("Pipeline").target("Root").target("Loop").target("slot").index(0)` |
| `builder.Root.body.add.Step(order=0)` | `builder.instance("Root").target("body").add("Step", order=0)` |
| `builder.Root.body.add.Step[2](order=2)` | `builder.instance("Root").target("body").add("Step", indexes=(2,), order=2)` |
| `builder.assign.Step.total.to().Root.total` | `builder.assign(source_instance="Step", inner_name="total", target_instance="Root", outer_name="total")` |
| `builder.assign.Step.total.to().Pipeline.Root.Inner.total` | `builder.assign(source_instance="Step", inner_name="total", target_instance="Pipeline", target_ref_path=("Root", "Inner"), outer_name="total")` |
| `builder.assign.Pipeline.Root.Inner.total.to().Init.total` | `builder.assign(source_instance="Pipeline", source_ref_path=("Root", "Inner"), inner_name="total", target_instance="Init", outer_name="total")` |
| `builder.bind_identifier.Step.total.to().Pipeline.Root.Inner.total` | `builder.bind_identifier(source_instance="Step", identifier=demand_descriptor, target_instance="Pipeline", to=supply_descriptor)` |

For systems that already hold a normalized target reference, `builder.target`
constructs the same target handle directly:

```python
b.target(
    root_instance="Pipeline",
    ref_path=("Root", "Loop"),
    target_name="slot",
    leaf_path=(0,),
).add("Step")
```

`builder.target(...)` also accepts descriptor target data from
`Composable.describe()`:

```python
hole = built.describe().single_hole_named("slot")
b.add("Pipeline", built)
b.target(hole.with_root_instance("Pipeline")).add("Step")
```

Passing an unresolved descriptor address raises; descriptor addresses become
executable only after a root instance is supplied.

When an address object is passed, explicit keyword overrides are allowed only if
they match the address. A conflicting `root_instance`, `target_name`,
`ref_path`, or `leaf_path` raises before any graph edge is recorded.

Descriptor data can also drive direct identifier binding. Identifier demand and
supply descriptors carry the descendant `ref_path` values accepted by
`builder.bind_identifier(...)`:

```python
demand = step.describe().identifier_demands[0]
supply = built.describe().identifier_supplies[0]

b.bind_identifier(
    source_instance="Step",
    identifier=demand,
    target_instance="Pipeline",
    to=supply,
)
```

`bind_identifier(...)` is direct and scope-aware: it resolves the source demand
to the selected supply before final hygiene, and the normal hygiene pass owns
the final spelling. Use `builder.assign(...)` when the desired behavior is the
graph-qualified assign alias.

See [descriptor-api.md](descriptor-api.md) for the full descriptor object model
and descriptor-driven builder workflow.

## Raw / assembler layer

A lower-level explicit API (instance ids, `PortId`, `tie`, …) exists for tooling
and tests; it is **semantics-equivalent** to fluent/handle surfaces with more
boilerplate.

## `build(unroll="auto")` on the graph

Calling **`.build()`** on the builder **folds** the graph into one **new**
`Composable`. The result **may still contain**:

- open **boundary** holes that were left unwired
- **loops** from `astichi_for` when unrolling was not requested or needed
- **exports** and other marker-lowered structure  

`BuilderHandle.build` currently accepts `unroll=True | False | "auto"`:

- `"auto"` (default) unrolls iff indexed target paths such as `A.slot[0]`
  require it
- `True` always unrolls `astichi_for(...)` loops before edge resolution
- `False` never unrolls and rejects indexed edges that require unrolled targets

## Variadic `order`

When multiple inserts target the same variadic hole, each edge carries an
**`order`** value: **lower sorts first**. **Equal `order`** ties resolve by
**first-added edge first**.

## See also

- [Addressing](addressing.md)
- **[§8 — Builder API](../../dev-docs/historical/AstichiApiDesignV1.md)**
