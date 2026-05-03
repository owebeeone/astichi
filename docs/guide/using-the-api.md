# Using the API

This guide walks through the main pipeline: **compile** a snippet, **compose**
with the builder, **materialize** for a runnable target, then **emit** source.

## 1. Imports

```python
import astichi
from astichi import Composable, build
from astichi.emit import verify_round_trip
```

Astichi currently recognizes marker names from the **source text** you pass to
`astichi.compile(...)`. There is **no** runtime `astichi.markers` shim module in
the package today, so the examples below place marker-bearing code directly in
the compiled source string.

## 2. Compile a snippet

`compile` parses marker-bearing source and returns a **`Composable`**. Pass
**origin** metadata so diagnostics and `ast` line numbers match the real
container (for example a slice extracted from a `.yidl` file).

```python
root_src = """
def run():
    astichi_hole(body)
"""

root = astichi.compile(
    root_src,
    file_name="snippet.py",
    line_number=1,
    offset=0,
)
assert isinstance(root, Composable)
```

The returned value carries **source origin** (`file_name`, line, offset) for
errors and provenance.

## 3. Bind compile-time externals

`astichi_bind_external(name)` declares a compile-time input. The current
frontend returns a concrete composable that supports **`.bind(...)`**, which
replaces those sites with literal AST values and returns a new immutable
composable.

```python
bound = astichi.compile(
    """
astichi_bind_external(fields)
print(fields)
""",
    file_name="externals.py",
).bind(fields=("a", "b"))
```

Keyword bindings and mapping bindings are both supported; kwargs win on key
collision.

## 4. Compose with the builder

Create a builder with **`build()`**, register named **instances** of
`Composable`, and **insert** into holes with an explicit **`order`** when
several fragments attach to the same variadic site.

```python
child = astichi.compile(
    "value = 1\nprint(value)\n",
    file_name="child.py",
)

builder = build()
builder.add.Root(root)
builder.add.Child(child)
builder.Root.body.add.Child(order=10)

graph = builder.build()
```

If you use indexed targets such as `builder.Root.slot[0]`, `builder.build()`
defaults to `unroll="auto"` and unrolls `astichi_for(...)` sites as needed for
those indexed edges.

The same builder graph can be driven by data instead of fluent attribute
chains. The named API is useful when instance names, target paths, or edge
overlays come from configuration or descriptor inspection:

```python
builder = build()
builder.add("Root", root)
builder.add("Child", child)
builder.instance("Root").target("body").add("Child", order=10)
graph = builder.build()
```

If a later stage reuses a built composable, descendant paths stay fluent:

```python
builder.Pipeline.Root.Parse.body.add.Step(order=0)
builder.assign.Step.total.to().Pipeline.Root.Right.total
```

The same fluent descendant syntax appears in emitted block-shell metadata as
`@astichi_insert(..., ref=Pipeline.Root.Parse)`. That marker is internal
metadata; authored snippets should use holes and builder wiring instead.

`build()` on the graph returns a **new** `Composable`. Boundary **holes** may
still be open if you chose not to wire every demand.

## 5. Inspect descriptors and drive the builder

Use **`.describe()`** when a tool needs to inspect a composable before deciding
how to wire it. Descriptors expose additive holes, target addresses, external
binds, identifier demands/supplies, add cardinality, and conservative
production compatibility.

Descriptor target references map directly to the data-driven builder API:

```python
stage1 = build()
stage1.add(
    "Root",
    astichi.compile(
        """
result = []
astichi_hole(cells)
astichi_hole(consumers)
final = tuple(result)
"""
    ),
)
stage1.add(
    "Cell",
    astichi.compile(
        """
shared = 10
astichi_export(shared)
"""
    ),
)
stage1.instance("Root").target("cells").add("Cell")
pipeline = stage1.build()

consumer = astichi.compile(
    """
astichi_import(shared)
astichi_pass(result, outer_bind=True).append(shared + 5)
"""
)

pipeline_desc = pipeline.describe()
consumer_hole = pipeline_desc.single_hole_named("consumers")
shared_supply = next(
    supply for supply in pipeline_desc.identifier_supplies
    if supply.name == "shared" and supply.ref_path == ("Root", "Cell")
)
shared_demand = consumer.describe().identifier_demands[0]

stage2 = build()
stage2.add("Pipeline", pipeline)
stage2.add("Consumer", consumer)
stage2.target(consumer_hole.with_root_instance("Pipeline")).add("Consumer")
stage2.bind_identifier(
    source_instance="Consumer",
    identifier=shared_demand,
    target_instance="Pipeline",
    to=shared_supply,
)

graph = stage2.build()
```

In this example, `consumer_hole.address` contains the descriptor target data:
the descendant path inside the staged `pipeline` composable and the target hole
name. `with_root_instance("Pipeline")` resolves that address against the
builder instance, and `stage2.target(...)` creates the same target handle as the
equivalent fluent path. The identifier descriptors bind the consumer demand to
the selected staged supply with `bind_identifier(...)`; final spelling is still
handled by normal hygiene.

External binds are also visible through descriptors:

```python
template = astichi.compile(
    """
label = astichi_bind_external(label)
result = label
"""
)
values = {"label": "ready"}
bind_values = {
    item.name: values[item.name]
    for item in template.describe().external_binds
    if not item.already_bound
}
bound = template.bind(bind_values)
```

See [Descriptor API](../reference/descriptor-api.md) for the full descriptor
surface and [Builder API](../reference/builder-api.md) for the data-driven
builder signatures.

## 6. Materialize

When all **mandatory** demands for your target are satisfied and **hygiene**
checks pass, call **`materialize()`** to obtain a representation suitable for
execution or final emission (expression, `def`, class body, module—per your
target contract).

```python
closed = graph.materialize()
```

If a required hole is missing or a name rule is violated, **`materialize`**
raises with a diagnostic.

Managed `astichi_pyimport(...)` declarations are also realized here. The marker
is removed, the imported local participates in hygiene, and the final module
receives an ordinary Python import statement.

## 7. Emit

Produce Python **source** for inspection, tests, or downstream tools.

```python
text = closed.emit(provenance=True)   # default: append provenance tail
text_plain = closed.emit(provenance=False)
verify_round_trip(text)
```

With **`provenance=True`**, emitted text ends with one trailing comment of the
form `# astichi-provenance: ...`. The emitted Python body remains authoritative;
the provenance payload is only for AST/source-location restoration and
round-trip checks. See [Materialize and emit](../reference/materialize-and-emit.md).

## 8. Where to read next

- [Reference index](../reference/README.md)
- [Managed Python imports](../reference/marker-pyimport.md)
- [Descriptor API](../reference/descriptor-api.md)
- [Builder API](../reference/builder-api.md)
- **[`AstichiSingleSourceSummary.md`](../../dev-docs/AstichiSingleSourceSummary.md)** — current snapshot and open gaps
